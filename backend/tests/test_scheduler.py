"""
日报调度器单测（不依赖真实数据库/Redis）：
- next_run_dt 计算正确（今天该时刻未过→今天；已过→明天）
- start_scheduler 在启用时补跑昨天并起后台任务；stop_scheduler 能取消
- 禁用时 start_scheduler 不起任务
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.core import scheduler
from app.core.config import settings


def test_next_run_dt_later_today():
    # 当前 01:00，hour=2 → 今天 02:00
    nxt = scheduler.next_run_dt(2, now=datetime(2026, 9, 4, 1, 0, 0))
    assert nxt == datetime(2026, 9, 4, 2, 0, 0)


def test_next_run_dt_rolls_to_tomorrow():
    # 当前 03:00，hour=2 已过 → 明天 02:00
    nxt = scheduler.next_run_dt(2, now=datetime(2026, 9, 4, 3, 0, 0))
    assert nxt == datetime(2026, 9, 5, 2, 0, 0)


@pytest.mark.asyncio
async def test_start_stop_scheduler_enabled(monkeypatch):
    # 启用：start 应补跑昨天（run_daily_summary 被调用一次）并创建后台任务
    calls = {"n": 0}

    async def fake_run(target_date=None):
        calls["n"] += 1
        calls["date"] = target_date

    monkeypatch.setattr(scheduler, "run_daily_summary", fake_run)
    monkeypatch.setattr(settings, "DAILY_SUMMARY_ENABLED", True)

    await scheduler.start_scheduler()
    try:
        assert scheduler._task is not None
        # 启动补偿应汇总“昨天”
        assert calls["n"] == 1
        assert calls["date"] == date.today() - timedelta(days=1)
    finally:
        await scheduler.stop_scheduler()
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_start_scheduler_disabled_no_task(monkeypatch):
    monkeypatch.setattr(settings, "DAILY_SUMMARY_ENABLED", False)
    await scheduler.start_scheduler()
    assert scheduler._task is None
