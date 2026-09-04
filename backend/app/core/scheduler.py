"""
日报定时汇总调度器（轻量 asyncio 实现，不引入额外调度依赖）。

设计要点：
- 汇总写入（daily_summary.py）全部是 ON DUPLICATE KEY UPDATE，按 (summary_date, ...) 幂等
  upsert。因此多 worker 各自起一个调度任务重复触发也不会产生重复行，无需分布式锁。
- 启动期补跑昨天：服务停机错过 02:00 触发点时，启动后立即补一次（幂等，安全）。
- 每日在本地时间 DAILY_SUMMARY_HOUR 点触发，汇总前一天数据。
- 关闭期 cancel 任务；任务内异常被吞掉并记录，不拖垮主事件循环。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from app.core.config import settings
from app.services.daily_summary import run_daily_summary

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def next_run_dt(hour: int, now: datetime | None = None) -> datetime:
    """计算下一次触发时间（本地时间）。若今天该时刻已过，则顺延到明天。

    now 可注入，便于测试；生产路径不传，使用当前时间。
    """
    now = now or datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


async def _loop() -> None:
    hour = settings.DAILY_SUMMARY_HOUR
    try:
        while True:
            target = next_run_dt(hour)
            sleep_secs = (target - datetime.now()).total_seconds()
            logger.info(f"[scheduler] next daily-summary at {target} (in {sleep_secs:.0f}s)")
            await asyncio.sleep(sleep_secs)
            # 跨日/启动补偿：汇总昨天（幂等 upsert）
            try:
                await run_daily_summary(date.today() - timedelta(days=1))
            except Exception as e:  # noqa: BLE001 - 调度任务异常不能拖垮主循环
                logger.error(f"[scheduler] daily-summary trigger failed: {e}", exc_info=True)
    except asyncio.CancelledError:
        logger.info("[scheduler] daily-summary task cancelled")
        raise


async def start_scheduler() -> None:
    """启动调度器：先补跑昨天，再起后台循环任务。"""
    global _task
    if not settings.DAILY_SUMMARY_ENABLED:
        logger.info("[scheduler] daily-summary disabled by config (DAILY_SUMMARY_ENABLED=false)")
        return
    # 启动补偿：服务停机错过触发点时补跑昨天（幂等，安全）
    try:
        await run_daily_summary(date.today() - timedelta(days=1))
    except Exception as e:  # noqa: BLE001
        logger.error(f"[scheduler] startup backfill failed: {e}", exc_info=True)
    _task = asyncio.create_task(_loop())
    logger.info("[scheduler] daily-summary scheduler started")


async def stop_scheduler() -> None:
    """关闭调度器：取消后台任务并等待其退出。"""
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
        logger.info("[scheduler] daily-summary scheduler stopped")
