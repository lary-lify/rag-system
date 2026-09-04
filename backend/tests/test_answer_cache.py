"""
答案级缓存（Q8.1）单测（fakeredis 模拟 Redis，无需真实服务）。

验证点：
- 问题归一化：空白压缩、小写
- scope 隔离：kb_ids 排序等价、空集合记为 kb:none
- 精确命中：同一归一化问题命中；字面不同但归一化相同也精确命中
- scope 不串味：不同 KB 集合互不命中
- 关闭开关：CACHE_ANSWER_ENABLED=false 时 lookup 返回 None、store 不写
- 语义命中：默认向量下不同字面问题余弦=1 命中
- 语义阈值闸门：正交向量余弦=0 不命中
- embedding 失败降级：lookup 返回 None 不抛
- 后端切换：enable_redis 后写入可被另一实例读到（多 worker 共享）
"""
import asyncio

import fakeredis
import pytest

from app.core.cache import Cache, answer_cache
from app.core.config import settings
from app.services import answer_cache as ac_mod
from app.services.answer_cache import (
    build_answer_scope,
    lookup_answer,
    normalize_query,
    store_answer,
)


@pytest.fixture
def redis_backend():
    """用 fakeredis 作为答案缓存后端，模拟多 worker 共享同一份。

    每个测试用独立的 FakeServer，避免 fakeredis 默认服务端在进程内跨测试共享
    导致答案键互相污染（实测会跨测试命中上一个测试写入的键）。
    """
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeStrictRedis(server=server, decode_responses=True)
    answer_cache.enable_redis(fake)
    yield
    answer_cache.disable_redis()


@pytest.fixture
def fake_embed(monkeypatch):
    """确定性 embedding：默认返回固定向量（任意两问题余弦≈1，足以触发语义命中路径）；
    测试可在 embed_map 里为特定问题注册自定义向量以验证阈值闸门。"""
    embed_map: dict[str, list[float]] = {}

    async def fake_embed_single(text, model=None, dimensions=None):
        if text in embed_map:
            return list(embed_map[text]), 0
        return [0.1] * 128, 0

    monkeypatch.setattr(ac_mod, "embed_single_text", fake_embed_single)
    return embed_map


def test_normalize_query():
    assert normalize_query("  退款 怎么弄？ ") == "退款 怎么弄？"
    assert normalize_query("How ARE you") == "how are you"


def test_scope_isolation():
    assert build_answer_scope([2, 1]) == "kb:1,2"
    assert build_answer_scope([1, 2]) == "kb:1,2"  # 排序等价
    assert build_answer_scope(None) == "kb:none"
    assert build_answer_scope([]) == "kb:none"


@pytest.mark.asyncio
async def test_exact_hit(redis_backend, fake_embed, monkeypatch):
    # 默认 CACHE_ANSWER_ENABLED=True，无需显式开启
    scope = build_answer_scope([1])
    # 先 miss
    r1 = await lookup_answer(scope, "怎么退款")
    assert r1.answer is None
    # 写回
    await store_answer(scope, r1.norm_q, "退款流程：...", query_vec=r1.query_vec)
    # 再查命中（归一化一致）
    assert (await lookup_answer(scope, "怎么退款")).answer == "退款流程：..."
    # 字面不同但归一化后相同（多余空白被压缩）-> 精确命中
    assert (await lookup_answer(scope, "  怎么退款  ")).answer == "退款流程：..."


@pytest.mark.asyncio
async def test_scope_no_cross_hit(redis_backend, fake_embed, monkeypatch):
    s1 = build_answer_scope([1])
    r = await lookup_answer(s1, "怎么退款")
    await store_answer(s1, r.norm_q, "A", query_vec=r.query_vec)
    # 不同 scope 不应命中
    s2 = build_answer_scope([2])
    assert (await lookup_answer(s2, "怎么退款")).answer is None


@pytest.mark.asyncio
async def test_disabled_returns_none(redis_backend, fake_embed, monkeypatch):
    # pydantic-settings 在导入期缓存 env，必须直接 patch 属性而非 setenv
    monkeypatch.setattr(settings, "CACHE_ANSWER_ENABLED", False)
    r = await lookup_answer(build_answer_scope([1]), "怎么退款")
    assert r.answer is None
    # store 也应被开关拦下，不写缓存
    await store_answer(build_answer_scope([1]), r.norm_q, "X", query_vec=r.query_vec)
    monkeypatch.setattr(settings, "CACHE_ANSWER_ENABLED", True)
    assert (await lookup_answer(build_answer_scope([1]), "怎么退款")).answer is None


@pytest.mark.asyncio
async def test_semantic_hit(redis_backend, fake_embed, monkeypatch):
    monkeypatch.setattr(settings, "ANSWER_SEMANTIC_THRESHOLD", 0.9)
    scope = build_answer_scope([1])
    # 存储：默认向量 [0.1]*128
    r = await lookup_answer(scope, "如何申请退款")
    await store_answer(scope, r.norm_q, "申请退款步骤", query_vec=r.query_vec)
    # 不同字面问题，默认向量与存储相同 -> 余弦=1 -> 语义命中
    assert (await lookup_answer(scope, "退款申请流程是什么")).answer == "申请退款步骤"


@pytest.mark.asyncio
async def test_semantic_threshold_gating(redis_backend, fake_embed, monkeypatch):
    monkeypatch.setattr(settings, "ANSWER_SEMANTIC_THRESHOLD", 0.9)
    scope = build_answer_scope([1])
    # 存储问题映射到向量 A（第一维为 1，其余为 0）
    fake_embed["如何申请退款"] = [1.0] + [0.0] * 127
    r = await lookup_answer(scope, "如何申请退款")
    await store_answer(scope, r.norm_q, "答案X", query_vec=r.query_vec)
    # 查询问题映射到正交向量 B（末维为 1）-> 余弦=0 -> 不应命中
    fake_embed["完全无关的问题xyz"] = [0.0] * 127 + [1.0]
    assert (await lookup_answer(scope, "完全无关的问题xyz")).answer is None


@pytest.mark.asyncio
async def test_embed_failure_degrades(monkeypatch):
    """embedding 抛错时 lookup 降级为未命中，不向上抛。"""

    async def boom(text, model=None, dimensions=None):
        raise RuntimeError("no network")

    monkeypatch.setattr(ac_mod, "embed_single_text", boom)
    monkeypatch.setattr(settings, "CACHE_ANSWER_ENABLED", True)
    r = await lookup_answer(build_answer_scope([1]), "怎么退款")
    assert r.answer is None


@pytest.mark.asyncio
async def test_shared_across_instances(redis_backend, fake_embed, monkeypatch):
    """写入落到共享 Redis 后端，另一个进程（复用同一 fake redis 的 Cache 实例）能命中。"""
    monkeypatch.setenv("CACHE_ANSWER_ENABLED", "true")
    scope = build_answer_scope([1])
    r = await lookup_answer(scope, "共享问题")
    await store_answer(scope, r.norm_q, "共享答案", query_vec=r.query_vec)

    # 模拟另一个 worker：新建 Cache 实例但接入同一个 fake redis 服务端。
    # redis_backend fixture 用 fakeredis.FakeStrictRedis() 默认独立服务端，这里
    # 用 FakeRedisServer 共享，确保两个客户端连的是同一份数据。
    import fakeredis as _fr

    server = _fr.FakeServer()
    # 重新把 answer_cache 接到这个可控服务端，便于第二个实例复用
    answer_cache.enable_redis(_fr.FakeStrictRedis(server=server, decode_responses=True))
    r2 = await lookup_answer(scope, "共享问题")
    await store_answer(scope, r2.norm_q, "共享答案", query_vec=r2.query_vec)

    other = Cache("answer", max_size=2000, ttl=3600.0)
    other.enable_redis(_fr.FakeStrictRedis(server=server, decode_responses=True))
    assert other.get(_exact_full(scope, r2.norm_q)) == "共享答案"


def _exact_full(scope_key: str, norm_q: str) -> str:
    from app.core.cache import make_cache_key

    return make_cache_key("answer", "exact", scope_key, norm_q)
