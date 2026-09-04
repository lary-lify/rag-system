"""
应用 lifespan 集成测试：验证启动/关闭期确实接好了缓存配置与日报调度器。

不依赖真实 MySQL / Redis / Milvus：把外部依赖的启动/关闭步骤 mock 成 noop，
只验证「main.py 的 lifespan 真的调用了 configure_caches / start_scheduler / stop_scheduler」。
这样若有人误删 lifespan 里的 start_scheduler() 调用，本测试会立刻红——单测只覆盖函数本身，
覆盖不到「被 lifespan 调用」这个接线点。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_lifespan_wires_cache_and_scheduler(monkeypatch):
    from app.main import app

    # 记录调度器启停
    calls = {"start": 0, "stop": 0}

    async def fake_start():
        calls["start"] += 1

    async def fake_stop():
        calls["stop"] += 1

    # 启动期：mock 掉依赖外部服务的步骤
    async def noop_async():
        return None

    monkeypatch.setattr("app.main.configure_caches", noop_async)  # 避免连 Redis
    monkeypatch.setattr("app.main.init_db", noop_async)
    monkeypatch.setattr("init_data.create_super_admin", noop_async)
    monkeypatch.setattr("app.core.scheduler.start_scheduler", fake_start)
    monkeypatch.setattr("app.core.scheduler.stop_scheduler", fake_stop)

    # 关闭期：Milvus 不连真服务
    fake_conn = MagicMock()
    fake_conn.disconnect = MagicMock()
    monkeypatch.setattr("app.main.get_milvus_connection", lambda: fake_conn)
    monkeypatch.setattr("app.services.milvus_service.shutdown_pool", lambda: None)

    async with app.router.lifespan_context(app):
        # 启动期应已调用 start_scheduler
        assert calls["start"] == 1, "lifespan 启动期应恰好调用一次 start_scheduler"

    # 关闭期应调用 stop_scheduler
    assert calls["stop"] == 1, "lifespan 关闭期应恰好调用一次 stop_scheduler"
