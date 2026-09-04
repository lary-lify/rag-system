"""
答案级缓存（Q8.1 落地 MVP）。

在 SSE 对话链路最前端复用「问题→答案」：命中后直接流式返回，跳过查询改写、
向量检索与 LLM 生成，是整条链路里最靠前的热点复用（整段答案复用，而非单条
embedding 或单条改写结果）。

双通道命中：
- 精确命中：原始问题归一化后 sha256，作为精确键查缓存（最快、零额外计算）。
- 语义命中：原始问题做 embedding，与「近期 query 向量池」逐条算余弦，取最近一条；
  相似度 >= ANSWER_SEMANTIC_THRESHOLD 即命中（捕捉同义改写，如「怎么退款」vs「退款流程」）。

scope 隔离：按知识库集合（kb_ids 排序）成键。同一 KB 集合下不同用户、不同对话共享
命中——因为 RAG 答案本质是「问题 + 该 KB 内容」的纯函数，共享既正确又最大化命中率。
仅当 kb_ids 非空且本次检索到片段时才写回，避免把「知识库无相关信息」这类拒答固化进缓存。

陈旧性：TTL 是答案陈旧的上界。KB 内容更新后，旧答案最多存活 CACHE_ANSWER_TTL 秒，
之后自然失效重新生成。MVP 不接文档级失效（那需要写时反查受影响问题，复杂度高）。

语义向量池：每个 scope 维护一个「近期 query 向量」有界队列（FIFO），落缓存后端。
命中时只在池内扫描，不枚举全量缓存，复杂度 O(pool_size)。池仅用于召回增强，丢失
（并发覆盖/淘汰）不影响正确性，最多降低语义命中率。
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.core.cache import answer_cache, make_cache_key
from app.core.config import settings
from app.services.embedding_service import embed_single_text

logger = logging.getLogger(__name__)


def normalize_query(q: str) -> str:
    """问题归一化：去首尾空白、转小写、压缩连续空白。

    归一化让「退款 怎么弄？」与「退款怎么弄？」这类差异被精确通道吸收，
    不必都走语义通道。中文不区分大小写但统一 lower 不影响；英文同义更受益。
    """
    q = (q or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q


def build_answer_scope(kb_ids: Optional[list[int]]) -> str:
    """按知识库集合成 scope 键。

    排序保证 {1,2} 与 {2,1} 等价；空集合记为 kb:none（此时调用方应禁止写缓存，
    因为无 KB 的闲聊答案还依赖多轮历史，不在键内，跨对话共享会串味）。
    """
    if not kb_ids:
        return "kb:none"
    s = ",".join(str(k) for k in sorted(set(int(k) for k in kb_ids)))
    return f"kb:{s}"


def _exact_key(scope_key: str, norm_q: str) -> str:
    return make_cache_key("answer", "exact", scope_key, norm_q)


def _pool_key(scope_key: str) -> str:
    return make_cache_key("answer", "pool", scope_key)


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度。维度不等或任一侧为零向量返回 0（视为不相似）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na ** 0.5 * nb ** 0.5)


@dataclass
class AnswerCacheResult:
    """lookup_answer 的返回：命中即带 answer；query_vec 供写回时复用，避免重复 embedding。"""

    answer: Optional[str]
    query_vec: Optional[list[float]]
    norm_q: str


async def lookup_answer(scope_key: str, question: str) -> AnswerCacheResult:
    """查答案缓存，返回命中答案（或 None）以及本次查询向量（供写回复用）。

    精确通道命中即返回，不触发任何 embedding；仅精确未命中且开启语义时做一次 embedding
    用于向量池扫描。embedding/池读取任何异常都降级为未命中，不拖慢主链路。
    """
    norm_q = normalize_query(question)
    if not settings.CACHE_ANSWER_ENABLED:
        return AnswerCacheResult(answer=None, query_vec=None, norm_q=norm_q)

    # 1) 精确命中：零额外计算
    exact = answer_cache.get(_exact_key(scope_key, norm_q))
    if exact is not None:
        logger.debug(f"[answer-cache] exact hit (scope={scope_key})")
        return AnswerCacheResult(answer=exact, query_vec=None, norm_q=norm_q)

    # 2) 语义命中：embedding + 向量池扫描
    vec: Optional[list[float]] = None
    try:
        vec, _ = await embed_single_text(
            norm_q,
            model=settings.TONGYI_EMBEDDING_MODEL,
            dimensions=settings.TONGYI_EMBEDDING_DIMENSIONS,
        )
    except Exception as e:
        logger.warning(f"[answer-cache] embed for lookup failed, skip semantic: {e}")
        return AnswerCacheResult(answer=None, query_vec=None, norm_q=norm_q)

    if not vec:
        return AnswerCacheResult(answer=None, query_vec=None, norm_q=norm_q)

    pool = _load_pool(scope_key)
    best: Optional[dict[str, Any]] = None
    best_sim = 0.0
    for entry in pool:
        sim = _cosine(vec, entry.get("vec") or [])
        if sim > best_sim:
            best_sim = sim
            best = entry

    if best is not None and best_sim >= float(settings.ANSWER_SEMANTIC_THRESHOLD):
        logger.info(f"[answer-cache] semantic hit sim={best_sim:.3f} (scope={scope_key})")
        return AnswerCacheResult(answer=best.get("a"), query_vec=vec, norm_q=norm_q)

    return AnswerCacheResult(answer=None, query_vec=vec, norm_q=norm_q)


async def store_answer(
    scope_key: str,
    norm_q: str,
    answer: str,
    query_vec: Optional[list[float]] = None,
) -> None:
    """写回答案缓存：精确键 + （best-effort）语义向量池。

    仅当调用方确认本次答案值得缓存（kb_ids 非空且检索到片段）时调用。任一环节异常
    都只丢缓存、不影响主流程；精确键写入是最关键的，即使池更新失败也要保证它成功。
    """
    if not settings.CACHE_ANSWER_ENABLED or not answer:
        return

    ttl = float(settings.CACHE_ANSWER_TTL)
    # 精确键：最关键，必须成功
    answer_cache.set(_exact_key(scope_key, norm_q), answer, ttl=ttl)

    # 语义池：best-effort，失败不致命
    try:
        vec = query_vec
        if vec is None:
            vec, _ = await embed_single_text(
                norm_q,
                model=settings.TONGYI_EMBEDDING_MODEL,
                dimensions=settings.TONGYI_EMBEDDING_DIMENSIONS,
            )
        if vec:
            await _update_pool(scope_key, norm_q, answer, vec, ttl)
    except Exception as e:
        logger.warning(f"[answer-cache] pool update failed (non-fatal): {e}")


# ---- 语义向量池（有界 FIFO，落缓存后端）----

_pool_locks: dict[str, asyncio.Lock] = {}


def _pool_lock(scope_key: str) -> asyncio.Lock:
    """per-scope 锁，串行化本进程内的池读改写，降低并发覆盖概率。

    跨进程的并发覆盖仍可能发生（无分布式锁），但池仅用于召回增强，丢失不影响
    正确性，最多降低语义命中率——与 embedding/rewrite 缓存的取舍一致。
    """
    global _pool_locks
    lock = _pool_locks.get(scope_key)
    if lock is None:
        lock = asyncio.Lock()
        _pool_locks[scope_key] = lock
        if len(_pool_locks) > 512:
            # 锁表无界增长保护：只保留当前被持有的锁
            _pool_locks = {k: v for k, v in _pool_locks.items() if v.locked()}
    return lock


def _load_pool(scope_key: str) -> list[dict[str, Any]]:
    raw = answer_cache.get(_pool_key(scope_key))
    if not isinstance(raw, list):
        return []
    return raw


async def _update_pool(
    scope_key: str,
    norm_q: str,
    answer: str,
    vec: list[float],
    ttl: float,
) -> None:
    async with _pool_lock(scope_key):
        pool = _load_pool(scope_key)
        # 同问题已存在则先移除，刷新到队尾（避免重复堆积）
        pool = [e for e in pool if e.get("q") != norm_q]
        pool.append({"q": norm_q, "vec": vec, "a": answer})
        cap = max(1, int(settings.ANSWER_SEMANTIC_POOL_MAX))
        if len(pool) > cap:
            pool = pool[-cap:]
        answer_cache.set(_pool_key(scope_key), pool, ttl=ttl)
