"""
LLM Service - DeepSeek streaming chat API integration.
Handles multi-turn context, RAG prompt assembly, token counting.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx
from app.clients.http_client import http_client_context

from app.core.config import settings
from app.services.embedding_service import embed_single_text, estimate_token_count
from app.services.milvus_service import search_vectors

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个企业知识库问答助手。严格遵守以下规则：

1. 你只能基于下方提供的"参考资料"来回答用户的问题。
2. 如果参考资料中没有与问题相关的信息，必须回答："抱歉，知识库中没有找到相关信息。"
3. 禁止编造、推测或使用你自己的知识来回答问题。
4. 回答时要完整引用参考资料中的所有相关内容，不要遗漏关键信息（如不同场景下的不同数据）。使用 markdown 格式。
5. 如果用户的追问（如"那XX呢？"）涉及参考资料中已有的信息，请结合之前的对话上下文来理解问题含义并从参考资料中找到完整答案。
6. 使用与用户提问相同的语言回答。"""


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
    # 1. Build context from KB retrieval
    context_parts = []
    source_chunks_data = []

    # Build search query: for short follow-ups, prepend the last question
    search_query = question
    if len(question.strip()) < 15 and db and conversation_id:
        try:
            from app.models.message import Message
            from sqlalchemy import select
            prev = await db.execute(
                select(Message.question).where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc()).limit(1)
            )
            prev_q = prev.scalar_one_or_none()
            if prev_q:
                search_query = f"{prev_q} {question}"
        except Exception:
            pass

    # Use LLM to rewrite query for better retrieval (with fallback)
    try:
        rewrite_result = await rewrite_query(search_query)
        search_query = rewrite_result["rewritten_query"]
        logger.info(f"[query] Original: {question} -> Rewritten: {search_query}")
    except Exception as e:
        logger.warning(f"[query] Query rewrite failed, using original: {e}")

    if kb_ids:
        for kb_id in kb_ids:
            try:
                # Load KB config for embedding model
                from app.models.knowledge_base import KnowledgeBase
                kb_config = None
                if db:
                    from sqlalchemy import select as sa_select
                    kb_result = await db.execute(sa_select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
                    kb_config = kb_result.scalar_one_or_none()

                embedding_model = kb_config.embedding_model if kb_config else settings.TONGYI_EMBEDDING_MODEL
                embedding_dimensions = kb_config.embedding_dimensions if kb_config else settings.TONGYI_EMBEDDING_DIMENSIONS

                # Embed query with KB-specific model
                query_vec, _tok = await embed_single_text(search_query, model=embedding_model, dimensions=embedding_dimensions)

                # Use vector search (fallback to hybrid if configured)
                from app.services.milvus_service import search_vectors
                results = await search_vectors(kb_id, query_vec)

                # Filter out deleted documents
                if db and results:
                    doc_ids = list({r.get("document_id") for r in results if r.get("document_id")})
                    if doc_ids:
                        from app.models.document import Document
                        del_res = await db.execute(
                            select(Document.id).where(
                                Document.id.in_(doc_ids),
                                Document.is_deleted == True,
                            )
                        )
                        deleted_ids = set(r[0] for r in del_res.fetchall())
                        if deleted_ids:
                            results = [r for r in results if r.get("document_id") not in deleted_ids]

                # Use results directly (rerank disabled for stability)

                for r in results:
                    snippet = r.get("content", "")[:500]

                    # Resolve document name (non-critical, never blocks)
                    doc_name = "未知文档"
                    doc_id = r.get("document_id")
                    if doc_id:
                        try:
                            if db:
                                from app.models.document import Document
                                doc_res = await db.execute(
                                    select(Document.original_filename).where(Document.id == doc_id)
                                )
                                name_row = doc_res.scalar_one_or_none()
                                if name_row:
                                    doc_name = name_row
                        except Exception:
                            pass  # name lookup is cosmetic, don't block

                    context_parts.append(
                        f"[Source (score={r['score']})]: {snippet}"
                    )
                    source_chunks_data.append({
                        "chunk_id": r.get("chunk_id"),
                        "document_id": doc_id,
                        "document_name": doc_name,
                        "content": r.get("content", "")[:500],
                        "score": r["score"],
                    })
            except Exception as e:
                logger.warning(f"[llm] KB{kb_id} search failed: {e}")

    # 2. Build messages with conversation history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add previous context from this conversation (last 10 turns)
    if db and conversation_id:
        from app.models.message import Message
        from sqlalchemy import select
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

    # 4. Final usage event
    yield {
        "type": "usage",
        "input_tokens": input_tokens_est,
        "output_tokens": output_tokens_total,
    }
