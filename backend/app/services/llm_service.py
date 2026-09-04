"""
LLM Service - DeepSeek streaming chat API integration.
Handles multi-turn context, RAG prompt assembly, token counting.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

import httpx
from sqlalchemy import select

from app.clients.http_client import http_client_context
from app.core.cache import make_cache_key, query_rewrite_cache
from app.core.config import settings
from app.services.answer_cache import build_answer_scope, lookup_answer, store_answer
from app.services.embedding_service import embed_single_text, estimate_token_count
from app.services.milvus_service import search_vectors
from app.services.query_rewrite import rewrite_query

logger = logging.getLogger(__name__)


# 片段在上下文中的截断长度：过长会把 prompt 撑爆，过短又丢信息
SNIPPET_MAX_CHARS = 500

SYSTEM_PROMPT = """你是一个企业知识库问答助手。严格遵守以下规则：

1. 你只能基于下方提供的"参考资料"来回答用户的问题。
2. 如果参考资料中没有与问题相关的信息，必须回答："抱歉，知识库中没有找到相关信息。"
3. 禁止编造、推测或使用你自己的知识来回答问题。
4. 回答时要完整引用参考资料中的所有相关内容，不要遗漏关键信息（如不同场景下的不同数据）。使用 markdown 格式。
5. 如果用户的追问（如"那XX呢？"）涉及参考资料中已有的信息，请结合之前的对话上下文来理解问题含义并从参考资料中找到完整答案。
6. 使用与用户提问相同的语言回答。"""


async def _last_question(db, conversation_id: int) -> str | None:
    """取上一轮问题，用于补全追问里的指代（如"那XX呢？"）。"""
    from app.models.message import Message

    try:
        result = await db.execute(
            select(Message.question)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"[llm] last question lookup failed: {e}")
        return None


async def _rewrite_with_fallback(question: str, search_query: str) -> str:
    """
    查询改写，带开关、超时与缓存。

    改写是挡在检索前的一次完整 LLM 调用，它耗时多久用户就多等多久，
    且失败不影响主流程的正确性（回退原查询即可），因此必须能关、
    能超时降级、能缓存复用。
    """
    if not settings.QUERY_REWRITE_ENABLED:
        return search_query

    cache_on = settings.QUERY_REWRITE_CACHE_ENABLED
    key = make_cache_key("rewrite", search_query) if cache_on else None

    if key:
        cached = query_rewrite_cache.get(key)
        if cached is not None:
            return cached

    rewritten = search_query
    succeeded = False
    try:
        result = await asyncio.wait_for(
            rewrite_query(search_query),
            timeout=max(0.1, float(settings.QUERY_REWRITE_TIMEOUT)),
        )
        candidate = (result or {}).get("rewritten_query")
        if candidate:
            rewritten = candidate
            succeeded = True
    except asyncio.TimeoutError:
        logger.warning(f"[llm] query rewrite timed out after {settings.QUERY_REWRITE_TIMEOUT}s")
    except Exception as e:
        logger.warning(f"[llm] query rewrite failed, using original: {e}")

    # 只缓存真正改写成功的结果。
    # 若把降级后的原查询也写进缓存，上游一次抖动会被固化成整个 TTL 内的
    # 长期降级——上游恢复后该问题仍命中缓存，再也不会去尝试改写。
    if key and succeeded:
        query_rewrite_cache.set(key, rewritten)

    logger.info(f"[query] Original: {question} -> Rewritten: {rewritten}")
    return rewritten


async def _load_kb_configs(db, kb_ids: list[int]) -> dict[int, Any]:
    """一次查询拿到全部知识库的 embedding 配置，替代逐库查询。"""
    from app.models.knowledge_base import KnowledgeBase

    if db is None or not kb_ids:
        return {}
    try:
        result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids)))
        return {kb.id: kb for kb in result.scalars().all()}
    except Exception as e:
        logger.warning(f"[llm] KB config lookup failed: {e}")
        return {}


async def _filter_deleted_documents(db, results: list[dict]) -> list[dict]:
    """剔除已删除文档的片段，一次 IN 查询替代逐库判断。"""
    from app.models.document import Document

    if db is None or not results:
        return results
    doc_ids = {r["document_id"] for r in results if r.get("document_id")}
    if not doc_ids:
        return results
    try:
        deleted = await db.execute(
            select(Document.id).where(
                Document.id.in_(doc_ids),
                Document.is_deleted == True,  # noqa: E712
            )
        )
    except Exception as e:
        logger.warning(f"[llm] deleted-document filter failed, keeping all: {e}")
        return results
    removed = set(deleted.scalars().all())
    if not removed:
        return results
    return [r for r in results if r.get("document_id") not in removed]


async def _resolve_document_names(db, results: list[dict]) -> dict[int, str]:
    """一次 IN 查询拿到全部文档名。

    原实现对每个命中片段单独查一次文件名：Top-K 命中 N 条就是 N 次
    数据库往返。检索本身只要几毫秒，补名字反而成为主要耗时。
    """
    from app.models.document import Document

    if db is None or not results:
        return {}
    doc_ids = {r["document_id"] for r in results if r.get("document_id")}
    if not doc_ids:
        return {}
    try:
        rows = await db.execute(
            select(Document.id, Document.original_filename).where(Document.id.in_(doc_ids))
        )
        return {doc_id: name for doc_id, name in rows.all() if doc_id is not None}
    except Exception as e:
        logger.warning(f"[llm] document name lookup failed: {e}")
        return {}


async def _retrieve_from_kbs(
    kb_ids: list[int],
    search_query: str,
    db,
) -> list[dict]:
    """
    跨知识库并发检索，返回按相关度降序排列的片段。

    原实现串行遍历 kb_ids：K 个知识库就是 K 次串行往返，且每个库内部
    还要再查一次配置。现按 embedding 配置分组（同配置只向量化一次），
    组内多库并发，组间也并发。
    """
    configs = await _load_kb_configs(db, kb_ids)

    groups: dict[tuple[str, int], list[int]] = {}
    for kb_id in kb_ids:
        cfg = configs.get(kb_id)
        model = cfg.embedding_model if cfg else settings.TONGYI_EMBEDDING_MODEL
        dim = cfg.embedding_dimensions if cfg else settings.TONGYI_EMBEDDING_DIMENSIONS
        groups.setdefault((model, dim), []).append(kb_id)

    async def _search_group(model: str, dim: int, ids: list[int]) -> list[dict]:
        query_vec, _ = await embed_single_text(search_query, model=model, dimensions=dim)
        per_kb = await asyncio.gather(
            *[search_vectors(kb_id, query_vec) for kb_id in ids],
            return_exceptions=True,
        )
        hits: list[dict] = []
        for kb_id, res in zip(ids, per_kb):
            if isinstance(res, BaseException):
                logger.warning(f"[llm] KB{kb_id} search failed: {res}")
                continue
            for r in res or []:
                hits.append({**r, "kb_id": kb_id})
        return hits

    nested = await asyncio.gather(
        *[_search_group(model, dim, ids) for (model, dim), ids in groups.items()],
        return_exceptions=True,
    )

    results: list[dict] = []
    for group in nested:
        if isinstance(group, BaseException):
            logger.warning(f"[llm] KB group search failed: {group}")
            continue
        results.extend(group)

    results = await _filter_deleted_documents(db, results)
    # 并发执行后顺序不再确定，统一按相关度降序，让最相关的片段排在前面
    results.sort(key=lambda r: r.get("score", 0.0), reverse=True)

    # 全局 Top-K 截断。
    # RAG_TOP_K 限定的是「每个知识库」的召回量，跨 N 个库并发检索后候选池
    # 是 N x RAG_TOP_K 条；若不经截断全部拼进 prompt，知识库越多噪声越多——
    # 一是把真正相关的片段挤到中间（lost-in-the-middle），二是无谓抬高
    # input token 成本。截断放在过滤已删文档之后，避免把名额浪费在无效片段上。
    global_top_k = int(settings.RAG_GLOBAL_TOP_K or 0)
    if global_top_k > 0 and len(results) > global_top_k:
        logger.debug(
            f"[llm] global top-k truncation: {len(results)} -> {global_top_k} "
            f"across {len(kb_ids)} KB(s)"
        )
        results = results[:global_top_k]

    doc_names = await _resolve_document_names(db, results)
    chunks: list[dict] = []
    for r in results:
        doc_id = r.get("document_id")
        chunks.append({
            "chunk_id": r.get("chunk_id"),
            "document_id": doc_id,
            "document_name": doc_names.get(doc_id) or "未知文档",
            "content": (r.get("content") or "")[:SNIPPET_MAX_CHARS],
            "score": r.get("score", 0.0),
            "kb_id": r.get("kb_id"),
        })
    return chunks


async def stream_chat_response(
    question: str,
    user_id: int,
    conversation_id: int,
    kb_ids: list[int],
    db=None,
) -> AsyncIterator[dict]:
    """
    Stream a chat response from DeepSeek with RAG augmentation.
    
    Yields dict events:
      - {"type": "source", "chunks": [...]}  - retrieved source chunks info
      - {"type": "token", "content": "..."}   - streamed answer text chunk
      - {"type": "usage", "input_tokens": N, "output_tokens": N}  - final usage stats
    
    All token counts are recorded to DB for billing.
    """
    # 0. 答案级缓存（Q8.1 MVP）：在链路最前端尝试命中。
    # 命中则直接流式返回缓存答案，跳过查询改写+向量检索+LLM 生成（整条链路最大头的开销）。
    # scope 按知识库集合隔离；命中时 SSE 带 cache_hit 标记，计费记 0（不调用 LLM）。
    scope_key = build_answer_scope(kb_ids)
    cache_result = await lookup_answer(scope_key, question)
    if cache_result.answer is not None:
        yield {"type": "source", "chunks": [], "cache_hit": True}
        yield {"type": "token", "content": cache_result.answer}
        yield {
            "type": "usage",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_hit": True,
        }
        return
    # 未命中：lookup 顺带算出的查询向量留待写回语义池复用，避免重复 embedding
    query_vec_for_store = cache_result.query_vec

    # 1. Build context from KB retrieval
    context_parts = []
    source_chunks_data = []

    # Build search query: for short follow-ups, prepend the last question
    search_query = question
    if len(question.strip()) < 15 and db and conversation_id:
        prev_q = await _last_question(db, conversation_id)
        if prev_q:
            search_query = f"{prev_q} {question}"

    # Use LLM to rewrite query for better retrieval (switchable, cached, time-boxed)
    search_query = await _rewrite_with_fallback(question, search_query)

    if kb_ids:
        source_chunks_data = await _retrieve_from_kbs(kb_ids, search_query, db)
        context_parts = [
            f"[Source (score={c['score']})]: {c['content']}"
            for c in source_chunks_data
        ]

    # 2. Build messages with conversation history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add previous context from this conversation (last 10 turns)
    if db and conversation_id:
        from app.models.message import Message

        result = await db.execute(
            select(Message).where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc()).limit(20)  # last 10 Q&A pairs
        )
        history = list(reversed(result.scalars().all()))
        for msg in history[-18:]:  # keep last ~9 pairs
            messages.append({"role": "user", "content": msg.question})
            if msg.answer:
                messages.append({"role": "assistant", "content": msg.answer})

    # Add current question with RAG context
    full_question = question
    if context_parts:
        context_str = "\n\n".join(context_parts)
        full_question = (
            f"## Reference Materials:\n{context_str}\n\n"
            f"## User Question:\n{question}"
        )

    messages.append({"role": "user", "content": full_question})

    # Yield source chunks first
    yield {
        "type": "source",
        "chunks": source_chunks_data,
    }

    # 3. Call DeepSeek streaming API
    input_tokens_est = sum(estimate_token_count(m["content"]) for m in messages)
    output_tokens_total = 0
    answer_text = ""  # 累积完整答案，用于命中后写回答案缓存

    try:
        async with http_client_context() as client:
            response = await client.post(
                f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_CHAT_MODEL,
                    "messages": messages,
                    "stream": True,
                    "temperature": 0.3,
                    "max_tokens": 4096,
                },
                timeout=settings.SSE_TIMEOUT_MS / 1000.0,
            )
            response.raise_for_status()

            buffer = ""
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break

                try:
                    delta = json.loads(data_str)
                    choices = delta.get("choices", [])
                    if not choices:
                        continue
                    content = choices[0].get("delta", {}).get("content", "")
                    if content:
                        output_tokens_total += estimate_token_count(content)
                        answer_text += content
                        yield {"type": "token", "content": content}
                except json.JSONDecodeError:
                    continue

            # Try to get real token counts from usage if available
            # Note: streaming may not include usage; we use estimates + record actual when known

    except httpx.HTTPStatusError as e:
        error_body = ""
        try:
            error_body = e.response.text
        except Exception:
            pass
        logger.error(f"[llm] DeepSeek API error: {e.response.status_code} - {error_body}")
        error_msg = "AI服务暂时不可用，请稍后重试"
        if e.response.status_code == 429:
            error_msg = "AI服务请求过于频繁，请稍后重试"
        elif e.response.status_code == 401:
            error_msg = "AI服务认证失败"
        yield {"type": "token", "content": f"\n\n**错误：{error_msg}**"}
    except Exception as e:
        logger.error(f"[llm] Unexpected error: {e}")
        yield {"type": "token", "content": "\n\n**错误：系统异常，请稍后重试**"}

    # 4. 写回答案缓存（仅当命中 KB 且检索到片段，且非错误串：避免缓存拒答/错误/闲聊跨对话串味）
    if (
        kb_ids
        and source_chunks_data
        and answer_text
        and not answer_text.strip().startswith("**错误")
    ):
        try:
            await store_answer(
                scope_key,
                cache_result.norm_q,
                answer_text,
                query_vec=query_vec_for_store,
            )
        except Exception as e:
            logger.warning(f"[llm] answer cache store failed (non-fatal): {e}")

    # 5. Final usage event
    yield {
        "type": "usage",
        "input_tokens": input_tokens_est,
        "output_tokens": output_tokens_total,
        "cache_hit": False,
    }
