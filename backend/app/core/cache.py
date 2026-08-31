"""
进程内 TTL 缓存。

P0 阶段不引入 Redis，先提供一套接口稳定的本地缓存，承接两类热点：
查询向量与查询改写结果。两者的共同特征是读多写少、可接受短暂陈旧。

设计要点：
- TTL + LRU 双约束：既按时间失效，也按容量淘汰，避免无界增长
- 单飞（single flight）：同一 key 并发未命中时只计算一次，避免缓存击穿
  时大量并发请求同时打到外部 API
- 统计可观测：暴露命中率与容量，后续接入 Prometheus 时可直接复用

替换为 Redis 时只需实现同样的 get / set / get_or_compute 接口，
调用方无需改动。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

_MISSING = object()


@dataclass
class CacheStats:
    """缓存运行统计。"""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    computations: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return (self.hits / self.total) if self.total else 0.0


class TTLCache:
    """带容量上限的 TTL 缓存，内部按 LRU 淘汰。

    非协程安全的部分（字典读写）不含 await 点，在单线程事件循环下是安全的；
    计算阶段通过 per-key 的 asyncio.Lock 保证同一 key 只计算一次。
    """

    def __init__(self, name: str, max_size: int = 1000, ttl: float = 300.0):
        self.name = name
        self.max_size = max(1, int(max_size))
        self.ttl = float(ttl)
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._stats = CacheStats()

    # ---- 基础读写 ----

    def get(self, key: str) -> Any | None:
        """读取缓存，过期或不存在返回 None。"""
        item = self._data.get(key)
        if item is None:
            self._stats.misses += 1
            return None

        expire_at, value = item
        if expire_at <= time.monotonic():
            del self._data[key]
            self._stats.expirations += 1
            self._stats.misses += 1
            return None

        self._data.move_to_end(key)
        self._stats.hits += 1
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """写入缓存，超出容量时按 LRU 淘汰最久未使用项。"""
        lifetime = self.ttl if ttl is None else float(ttl)
        self._data[key] = (time.monotonic() + lifetime, value)
        self._data.move_to_end(key)

        while len(self._data) > self.max_size:
            self._data.popitem(last=False)
            self._stats.evictions += 1

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    # ---- 单飞 ----

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
            self._prune_locks()
        return lock

    def _prune_locks(self) -> None:
        """清理空闲的 per-key 锁，防止 key 基数大时锁表无界增长。

        只回收当前未被持有的锁；仍被持有的锁即便被遍历到也不会移除，
        因此不会影响正在进行的单飞。
        """
        if len(self._locks) <= self.max_size * 2:
            return
        self._locks = {k: v for k, v in self._locks.items() if v.locked()}

    async def get_or_compute(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: float | None = None,
    ) -> Any:
        """命中即返回，未命中则计算并回填。

        同一 key 的并发未命中只会触发一次 factory 调用，其余协程等待并
        复用结果，避免缓存失效瞬间把压力全部传导到外部 API。
        """
        cached = self.get(key)
        if cached is not None:
            return cached

        lock = self._lock_for(key)
        async with lock:
            # 拿到锁后再查一次：等待期间可能已有协程完成计算
            cached = self.get(key)
            if cached is not None:
                return cached

            value = await factory()
            self._stats.computations += 1
            self.set(key, value, ttl=ttl)
            return value

    # ---- 观测 ----

    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "size": len(self._data),
            "max_size": self.max_size,
            "ttl": self.ttl,
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "computations": self._stats.computations,
            "evictions": self._stats.evictions,
            "expirations": self._stats.expirations,
            "hit_rate": round(self._stats.hit_rate, 4),
        }


def make_cache_key(*parts: Any) -> str:
    """由任意可字符串化的片段生成定长缓存键。

    文本类入参可能很长（如整段 query），直接拼接会让键膨胀，
    统一做一次 sha256 摘要。
    """
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---- 全局缓存实例 ----
# 集中注册便于统一观测与后续替换后端。
embedding_cache = TTLCache(
    name="embedding",
    max_size=1000,
    ttl=86400.0,
)
query_rewrite_cache = TTLCache(
    name="query_rewrite",
    max_size=1000,
    ttl=3600.0,
)


def all_caches() -> list[TTLCache]:
    return [embedding_cache, query_rewrite_cache]


def configure_caches() -> None:
    """按当前配置刷新缓存参数，供启动时调用。"""
    from app.core.config import settings

    embedding_cache.max_size = settings.EMBEDDING_CACHE_MAX_SIZE
    embedding_cache.ttl = float(settings.EMBEDDING_CACHE_TTL)
    query_rewrite_cache.max_size = settings.QUERY_REWRITE_CACHE_MAX_SIZE
    query_rewrite_cache.ttl = float(settings.QUERY_REWRITE_CACHE_TTL)
    logger.info(
        f"[cache] configured: embedding(max={embedding_cache.max_size}, ttl={embedding_cache.ttl}s), "
        f"rewrite(max={query_rewrite_cache.max_size}, ttl={query_rewrite_cache.ttl}s)"
    )
