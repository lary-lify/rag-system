"""
Redis 客户端单例（async）。

属于 clients 层的一部分，主请求链路尚未使用；配置好 REDIS_URL 并安装
`redis` 后，即可用于限流 / 缓存 / 会话等场景（与脚手架 Base/Client/redisClient.py 对齐）。
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
