"""
Redis 缓存后端单测（fakeredis 模拟，无需真实 Redis 服务）。

验证点：
- RedisCache 的 get/set/get_or_compute 与 TTLCache 同接口、行为一致
- JSON 序列化 round-trip（embedding 向量 list[float]、rewrite dict）
- 跨进程共享：两个 RedisCache 实例（同一 fake redis）能互相读到写入
- Cache 外观后端切换：enable_redis 后 get/set 走 Redis；disable_redis 回退 memory
- 降级：configure_caches 在 redis 不可达时保持 memory、不抛
"""
import asyncio

import fakeredis
import pytest

from app.core import cache as cache_mod
from app.core.cache import (
    Cache,
    RedisCache,
    TTLCache,
    configure_caches,
    embedding_cache,
    query_rewrite_cache,
)


@pytest.fixture
def fake_redis():
    """同机 fake redis 服务端，模拟多 worker 共享同一份。"""
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_rediscache_set_get_roundtrip(fake_redis):
    rc = RedisCache("embedding", fake_redis, max_size=10, ttl=60)
    vec = [0.1, 0.2, -0.3] * 100  # 模拟 1024 维被截断，验证 float 精度往返
    rc.set("k1", vec)
    got = rc.get("k1")
    assert got == vec
    assert rc.stats()["hits"] == 1
    assert rc.stats()["misses"] == 0


def test_rediscache_rewrite_dict_roundtrip(fake_redis):
    rc = RedisCache("query_rewrite", fake_redis, max_size=10, ttl=60)
    payload = {"rewritten_query": "耳机防水吗", "query_variants": ["a", "b"], "analysis": "x", "original_query": "q"}
    rc.set("q", payload)
    assert rc.get("q") == payload


def test_rediscache_miss(fake_redis):
    rc = RedisCache("embedding", fake_redis, max_size=10, ttl=60)
    assert rc.get("nope") is None
    assert rc.stats()["misses"] == 1


def test_rediscache_get_or_compute_hits_once(fake_redis):
    rc = RedisCache("embedding", fake_redis, max_size=10, ttl=60)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return [1.0, 2.0]

    async def run():
        a = await rc.get_or_compute("key", factory)
        b = await rc.get_or_compute("key", factory)
        return a, b

    a, b = asyncio.run(run())
    assert a == b == [1.0, 2.0]
    assert calls["n"] == 1  # 仅计算一次，第二次命中


def test_rediscache_shared_across_instances(fake_redis):
    """两个 RedisCache（模拟两个 worker）共享同一 fake redis。"""
    rc1 = RedisCache("embedding", fake_redis, max_size=10, ttl=60)
    rc2 = RedisCache("embedding", fake_redis, max_size=10, ttl=60)
    rc1.set("shared", [9.0, 8.0])
    assert rc2.get("shared") == [9.0, 8.0]  # 跨实例可见


def test_rediscache_utilization_is_none(fake_redis):
    rc = RedisCache("embedding", fake_redis, max_size=10, ttl=60)
    rc.set("a", [1.0])
    assert rc.stats()["utilization"] is None


def test_cache_facade_switches_backend(fake_redis):
    c = Cache("embedding", max_size=10, ttl=60)
    assert c._active is c._memory  # 默认 memory
    c.enable_redis(fake_redis)
    assert isinstance(c._active, RedisCache)
    c.set("k", [3.0])
    assert c.get("k") == [3.0]  # 走 Redis
    c.disable_redis()
    assert c._active is c._memory


def test_configure_caches_redis_unreachable_downgrades(monkeypatch):
    """CACHE_BACKEND=redis 但 Redis 不可达 -> 保持 memory，不抛。"""
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1")  # 连不上的端口
    monkeypatch.setenv("REDIS_SYNC_AVAILABLE", "1")
    # 确保导入期已标记可用（requirements 含 redis）
    import redis as _rs

    monkeypatch.setattr(cache_mod, "_redis_sync", _rs)
    monkeypatch.setattr(cache_mod, "_REDIS_SYNC_AVAILABLE", True)

    async def run():
        await configure_caches()

    asyncio.run(run())
    # 全局实例应仍指向 memory 后端（降级）
    assert embedding_cache._active is embedding_cache._memory
    assert query_rewrite_cache._active is query_rewrite_cache._memory


def test_configure_caches_memory_backend(monkeypatch):
    monkeypatch.setenv("CACHE_BACKEND", "memory")
    async def run():
        await configure_caches()
    asyncio.run(run())
    assert embedding_cache._active is embedding_cache._memory
