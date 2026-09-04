"""
Redis 客户端单例（async）。

属于 clients 层的一部分。说明：
- 缓存（查询向量 / 查询改写）已通过 `app.core.cache` 接入，使用**同步** redis 客户端
  （与 TTLCache 同接口、调用方零改动），由 `CACHE_BACKEND=redis` 开启。
- 本文件的 async 客户端保留给未来需要异步语义的场景（限流 / 会话等）。
两者共用同一个 REDIS_URL，按需取用即可。
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    aioredis = None  # type: ignore
    _REDIS_AVAILABLE = False

_client = None


def get_redis_client():
    global _client
    if not _REDIS_AVAILABLE:
        raise RuntimeError("`redis` package is not installed. Run: pip install redis")
    if _client is None:
        from app.core.config import settings
        _client = aioredis.from_url(
            getattr(settings, "REDIS_URL", None) or os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis client initialized")
    return _client


async def close_redis_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
