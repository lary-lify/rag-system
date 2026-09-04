"""
Reranker 主链路接入验证（app/services/rerank_service.py + llm_service 接线）。

覆盖：
- 启发式 cross_encoder 重排按相关度（term overlap）把最相关片段顶到前面；
- 空候选安全返回空；
- rerank_results 给每个候选写入 rerank_score；
- LLM 打分模式网络失败时回退原序（主链路不崩）。

重要事实（证据型）：cross_encoder_similarity 用 `str.split()`（按空格分词）算 term
overlap。中文 query/文档整句无空格 → overlap 恒为 0，启发式实际只剩 position+length
信号，对中文相关度区分很弱。中文要真重排必须开 RERANKER_USE_LLM=True（DeepSeek 打分）。
因此单测用**英文** query 验证 heuristic 排序逻辑本身正确；中文质量靠 LLM 模式兜底。
"""
import pytest

from app.services import rerank_service as rerank_mod
from app.services.rerank_service import rerank_results


@pytest.mark.asyncio
async def test_heuristic_rerank_orders_by_relevance():
    """term overlap 高的文档应排到第一位。"""
    docs = [
        {"content": "the refund process requires logging into your account"},
        {"content": "today is a sunny day with no clouds at all"},
    ]
    reranked = await rerank_results(
        "what is the refund process", docs, top_k=2, use_llm=False
    )
    assert len(reranked) == 2
    assert reranked[0]["content"] == docs[0]["content"]


@pytest.mark.asyncio
async def test_rerank_empty_returns_empty():
    assert await rerank_results("anything", [], use_llm=False) == []
    assert await rerank_results("anything", [], use_llm=True) == []


@pytest.mark.asyncio
async def test_rerank_results_writes_rerank_score():
    docs = [
        {"content": "the refund process requires logging into your account"},
        {"content": "today is a sunny day with no clouds at all"},
    ]
    reranked = await rerank_results("refund process", docs, top_k=2, use_llm=False)
    for d in reranked:
        assert "rerank_score" in d
        assert isinstance(d["rerank_score"], (int, float))


@pytest.mark.asyncio
async def test_llm_rerank_falls_back_on_error(monkeypatch):
    """LLM 打分模式网络失败时回退原序，不抛异常、不拖垮主链路。"""

    class _BoomClient:
        async def post(self, *a, **k):
            raise RuntimeError("network down")

    class _BoomCtx:
        async def __aenter__(self):
            return _BoomClient()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(rerank_mod, "http_client_context", _BoomCtx())

    docs = [
        {"content": "alpha refund steps"},
        {"content": "beta weather report"},
        {"content": "gamma product manual"},
    ]
    # use_llm=True 会走 rerank_with_llm，网络失败 → 回退 documents[:top_k] 原序
    reranked = await rerank_results("refund", docs, top_k=3, use_llm=True)
    assert [d["content"] for d in reranked] == [d["content"] for d in docs[:3]]


# ---------- 主链路接线验证（证据型：确认 stream_chat_response 真的调了 rerank）----------
import app.services.llm_service as llm_service
from app.core.config import settings


@pytest.mark.asyncio
async def test_rerank_wired_into_main_path(monkeypatch):
    """RERANKER_ENABLED=True（默认）时，检索后主链路应调用 rerank_results。"""
    monkeypatch.setattr(settings, "CACHE_ANSWER_ENABLED", False)  # 关答案缓存，避免真实 embedding
    calls: list[dict] = []

    async def spy_rerank(**kwargs):
        calls.append(kwargs)
        return list(kwargs["documents"])  # 原序返回，不影响断言

    monkeypatch.setattr(llm_service, "rerank_results", spy_rerank)

    async def fake_retrieve(kb_ids, search_query, db):
        return [
            {"chunk_id": 2, "content": "irrelevant weather doc", "score": 0.9,
             "kb_id": 10, "document_id": 1, "document_name": "doc"},
            {"chunk_id": 1, "content": "refund steps here", "score": 0.8,
             "kb_id": 10, "document_id": 1, "document_name": "doc"},
        ]

    monkeypatch.setattr(llm_service, "_retrieve_from_kbs", fake_retrieve)

    async def fake_rewrite(q, sq):
        return sq

    monkeypatch.setattr(llm_service, "_rewrite_with_fallback", fake_rewrite)

    gen = llm_service.stream_chat_response(
        question="how to get a refund process", user_id=1,
        conversation_id=1, kb_ids=[10], db=None,
    )
    first = await gen.__anext__()  # source 事件在 LLM 调用之前 yield，取到即止
    await gen.aclose()

    assert first["type"] == "source"
    assert len(calls) == 1
    assert calls[0]["use_llm"] is False  # 默认启发式
    assert calls[0]["query"] == "how to get a refund process"
    # 传入 rerank 的候选 == 检索返回的候选
    assert [c["chunk_id"] for c in calls[0]["documents"]] == [2, 1]


@pytest.mark.asyncio
async def test_rerank_skipped_when_disabled(monkeypatch):
    """RERANKER_ENABLED=False 时，主链路不应调用 rerank_results。"""
    monkeypatch.setattr(settings, "CACHE_ANSWER_ENABLED", False)
    monkeypatch.setattr(settings, "RERANKER_ENABLED", False)
    called = {"n": 0}

    async def spy_rerank(**kwargs):
        called["n"] += 1
        return list(kwargs["documents"])

    monkeypatch.setattr(llm_service, "rerank_results", spy_rerank)

    async def _fake_rewrite(q, sq):
        return sq

    monkeypatch.setattr(llm_service, "_rewrite_with_fallback", _fake_rewrite)

    async def _fake_retrieve(kb_ids, search_query, db):
        return [
            {"chunk_id": 1, "content": "refund steps", "score": 0.8,
             "kb_id": 10, "document_id": 1, "document_name": "doc"},
        ]

    monkeypatch.setattr(llm_service, "_retrieve_from_kbs", _fake_retrieve)

    gen = llm_service.stream_chat_response(
        question="how to get a refund process", user_id=1,
        conversation_id=1, kb_ids=[10], db=None,
    )
    first = await gen.__anext__()
    await gen.aclose()

    assert first["type"] == "source"
    assert called["n"] == 0
