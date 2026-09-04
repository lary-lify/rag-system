"""
进程内 TTL 缓存，可切换为 Redis 共享缓存。

P0 阶段不引入 Redis，先提供一套接口稳定的本地缓存，承接两类热点：
查询向量与查询改写结果。两者的共同特征是读多写少、可接受短暂陈旧。

设计要点（进程内）：
- TTL + LRU 双约束：既按时间失效，也按容量淘汰，避免无界增长
- 单飞（single flight）：同一 key 并发未命中时只计算一次，避免缓存击穿
  时大量并发请求同时打到外部 API
- 统计可观测：暴露命中率与容量，后续接入 Prometheus 时可直接复用

Redis 后端（CACHE_BACKEND=redis）实现与 TTLCache 完全相同的 get / set /
get_or_compute 接口，调用方（embedding_service / query_rewrite）零改动；
多副本部署时缓存集中存储、重启不丢。连不上 Redis 时自动降级进程内并告警
（fail-safe），不阻塞启动。

替换为 Redis 时只需实现同样的 get / set / get_or_compute 接口，
调用方无需改动。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_MISSING = object()

# 同步 redis 客户端是否在运行环境可用（requirements 已含 redis>=5.0.0）。
# 用同步客户端是因为缓存的 get/set 必须保持与 TTLCache 完全相同的同步签名，
# 这样 embedding_service / query_rewrite 的调用方无需任何改动；同步读写在本地 /
# 同机 Redis 上仅亚毫秒级，热点小数据可接受。异步抛动由 try/except 兜底。
try:
    import redis as _redis_sync

    _REDIS_SYNC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _redis_sync = None  # type: ignore
    _REDIS_SYNC_AVAILABLE = False


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
        size = len(self._data)
        return {
            "name": self.name,
            "size": size,
            "max_size": self.max_size,
            "ttl": self.ttl,
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "computations": self._stats.computations,
            "evictions": self._stats.evictions,
            "expirations": self._stats.expirations,
            "hit_rate": round(self._stats.hit_rate, 4),
            # 容量水位：长期贴着 1 说明缓存装不下工作集，淘汰在持续发生，
            # 这时提命中率的手段是调大 max_size，而不是调 TTL。
            "utilization": round(size / self.max_size, 4) if self.max_size else 0.0,
        }


class RedisCache:
    """Redis 后端缓存，接口与 TTLCache 完全一致（get/set 同步，get_or_compute 异步）。

    集中式存储，多副本共享、重启不丢。容量与 TTL 由 Redis 服务端 maxmemory 策略
    与 key 的 EX 控制；本类的 max_size 在 Redis 模式下仅作展示，不强制本地 LRU。

    单飞：进程内 per-key asyncio.Lock 仍保留（防本进程同一事件循环内的击穿）；
    跨进程的并发未命中可能短暂重复计算，但 embedding 是纯函数、rewrite 失败会
    降级原始 query，重复计算幂等无害，因此不引入 Redis 分布式锁（避免复杂度与
    额外的 RTT）。
    """

    def __init__(self, name: str, client: Any, max_size: int = 1000, ttl: float = 300.0):
        self.name = name
        self._redis = client
        self.max_size = max(1, int(max_size))
        self.ttl = float(ttl)
        self._stats = CacheStats()
        self._locks: dict[str, asyncio.Lock] = {}

    # ---- key ----
    def _full_key(self, key: str) -> str:
        return f"rag:cache:{self.name}:{key}"

    # ---- 基础读写（同步，与 TTLCache 同签名） ----

    def get(self, key: str) -> Any | None:
        try:
            raw = self._redis.get(self._full_key(key))
        except Exception as e:  # Redis 抖动不应击穿到业务
            logger.warning(f"[cache:{self.name}] redis get failed, treat as miss: {e}")
            self._stats.misses += 1
            return None
        if raw is None:
            self._stats.misses += 1
            return None
        try:
            value = json.loads(raw)
        except Exception:
            self._stats.misses += 1
            return None
        self._stats.hits += 1
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        lifetime = int(self.ttl if ttl is None else float(ttl))
        try:
            self._redis.set(
                self._full_key(key),
                json.dumps(value, ensure_ascii=False),
                ex=lifetime,
            )
        except Exception as e:  # 写入失败只丢缓存，不影响主流程
            logger.warning(f"[cache:{self.name}] redis set failed, skip: {e}")

    # ---- 单飞 ----

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
            self._prune_locks()
        return lock

    def _prune_locks(self) -> None:
        if len(self._locks) <= self.max_size * 2:
            return
        self._locks = {k: v for k, v in self._locks.items() if v.locked()}

    async def get_or_compute(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: float | None = None,
    ) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached

        lock = self._lock_for(key)
        async with lock:
            cached = self.get(key)
            if cached is not None:
                return cached
            value = await factory()
            self._stats.computations += 1
            self.set(key, value, ttl=ttl)
            return value

    def invalidate(self, key: str) -> None:
        try:
            self._redis.delete(self._full_key(key))
        except Exception:
            pass

    def clear(self) -> None:
        try:
            keys = self._redis.keys(f"rag:cache:{self.name}:*")
            if keys:
                self._redis.delete(*keys)
        except Exception:
            pass

    def __len__(self) -> int:
        try:
            return len(self._redis.keys(f"rag:cache:{self.name}:*"))
        except Exception:
            return 0

    def stats(self) -> dict[str, Any]:
        size = len(self)
        return {
            "name": self.name,
            "size": size,
            "max_size": self.max_size,
            "ttl": self.ttl,
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "computations": self._stats.computations,
            "evictions": 0,
            "expirations": 0,
            "hit_rate": round(self._stats.hit_rate, 4),
            # 集中式缓存由 Redis 服务端 maxmemory 策略管容量，本进程无法估算水位；
            # 需要水位时查 Redis INFO memory / 监控 maxmemory-policy。
            "utilization": None,
        }


class Cache:
    """统一缓存外观：调用方持有稳定引用，后端在 memory / redis 间切换而不改引用。

    embedding_service / query_rewrite 在导入期绑定的是这个 Cache 实例，因此
    configure_caches() 只能在实例内部切换 _active 后端，不能替换全局变量对象。
    """

    def __init__(self, name: str, max_size: int = 1000, ttl: float = 300.0):
        self.name = name
        self._memory = TTLCache(name, max_size, ttl)
        self._redis: Optional[RedisCache] = None
        self._active: Any = self._memory

    def enable_redis(self, client: Any) -> None:
        self._redis = RedisCache(self.name, client, self._memory.max_size, self._memory.ttl)
        self._active = self._redis

    def disable_redis(self) -> None:
        self._active = self._memory

    def configure(self, max_size: int, ttl: float) -> None:
        self._memory.max_size = max(1, int(max_size))
        self._memory.ttl = float(ttl)
        if self._redis is not None:
            self._redis.max_size = self._memory.max_size
            self._redis.ttl = self._memory.ttl

    # ---- 委托给当前活动后端（签名与 TTLCache / RedisCache 完全一致） ----
    def get(self, key: str) -> Any | None:
        return self._active.get(key)

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._active.set(key, value, ttl)

    async def get_or_compute(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: float | None = None,
    ) -> Any:
        return await self._active.get_or_compute(key, factory, ttl)

    def invalidate(self, key: str) -> None:
        self._active.invalidate(key)

    def clear(self) -> None:
        self._active.clear()

    def __len__(self) -> int:
        return len(self._active)

    def stats(self) -> dict[str, Any]:
        return self._active.stats()


def make_cache_key(*parts: Any) -> str:
    """由任意可字符串化的片段生成定长缓存键。

    文本类入参可能很长（如整段 query），直接拼接会让键膨胀，
    统一做一次 sha256 摘要。
    """
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---- 全局缓存实例 ----
# 集中注册便于统一观测与后续替换后端。引用稳定，configure_caches() 只切换内部后端。
embedding_cache = Cache(
    name="embedding",
    max_size=1000,
    ttl=86400.0,
)
query_rewrite_cache = Cache(
    name="query_rewrite",
    max_size=1000,
    ttl=3600.0,
)


def all_caches() -> list[Cache]:
    return [embedding_cache, query_rewrite_cache]


_redis_client: Any = None


async def configure_caches() -> None:
    """按当前配置刷新缓存参数并选择后端。

    改为 async 是为了启动期能就近探测 Redis 连通性（ping 阻塞但仅一次）。
    连不上 Redis 时降级进程内并告警，保证启动不阻塞。
    """
    from app.core.config import settings

    embedding_cache.configure(settings.EMBEDDING_CACHE_MAX_SIZE, settings.EMBEDDING_CACHE_TTL)
    query_rewrite_cache.configure(settings.QUERY_REWRITE_CACHE_MAX_SIZE, settings.QUERY_REWRITE_CACHE_TTL)

    backend = str(getattr(settings, "CACHE_BACKEND", "memory")).lower()
    if backend == "redis":
        if not _REDIS_SYNC_AVAILABLE:
            logger.error("[cache] CACHE_BACKEND=redis 但 redis 库不可用，降级为进程内缓存")
        else:
            try:
                client = _redis_sync.from_url(  # type: ignore[union-attr]
                    settings.REDIS_URL,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                    decode_responses=True,
                )
                client.ping()
                global _redis_client
                _redis_client = client
                embedding_cache.enable_redis(client)
                query_rewrite_cache.enable_redis(client)
                logger.info(f"[cache] 后端=redis ({settings.REDIS_URL})，多副本共享缓存已启用")
            except Exception as e:
                logger.error(f"[cache] 连接 Redis 失败，降级为进程内缓存: {e}")
                embedding_cache.disable_redis()
                query_rewrite_cache.disable_redis()
    else:
        embedding_cache.disable_redis()
        query_rewrite_cache.disable_redis()

    logger.info(
        f"[cache] configured: embedding(max={embedding_cache._memory.max_size}, ttl={embedding_cache._memory.ttl}s), "
        f"rewrite(max={query_rewrite_cache._memory.max_size}, ttl={query_rewrite_cache._memory.ttl}s), "
        f"backend={backend}"
    )

    # 容量与内存占用本来是「配了就看不见」的东西：调大能提命中率，代价是
    # 常驻内存，而这两个缓存每进程一份，真实开销要按 worker 数放大。启动时
    # 把这笔账算出来，避免线上内存悄悄涨上去才发现是缓存配大了。
    #
    # 单条量级是估算：embedding 存 1024 维 float 列表，Python 下每个 float
    # 对象 24B 加 8B 指针 ≈ 32B/维，一条约 32KB；rewrite 存短字符串，按
    # 2KB/条估。量级对就够，不追求精确。
    est_bytes = embedding_cache._memory.max_size * 32 * 1024 + query_rewrite_cache._memory.max_size * 2 * 1024
    workers = max(1, int(settings.APP_WORKERS))
    if backend == "redis":
        logger.info(
            f"[cache] 后端=redis：缓存集中存储，{workers} 个 worker 共享同一份，重启不丢；"
            f"容量由 Redis 服务端 maxmemory 策略管理，不再按 worker 数折算本地内存。"
        )
    else:
        logger.info(
            f"[cache] 后端=memory：估算内存 ≈ {est_bytes / 1024 / 1024:.1f} MiB/进程，"
            f"按 APP_WORKERS={workers} 折算全机 ≈ {est_bytes * workers / 1024 / 1024:.1f} MiB；"
            f"缓存每进程一份，worker 越多单条命中率越低（同一 query 只落到一个 worker）。"
            f"接 Redis（CACHE_BACKEND=redis）后可统一共享。"
        )


def close_redis() -> None:
    """关闭 Redis 客户端连接（进程退出时调用）。"""
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None
