"""
Rerank Service - Cross-encoder based reranking for search results.
Uses LLM to rerank retrieval results for improved relevance.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from app.clients.http_client import http_client_context

from app.core.config import settings

logger = logging.getLogger(__name__)

RERANK_PROMPT = """你是一个文档相关性评估专家。给定一个用户查询和多个候选文档片段，请评估每个片段与查询的相关性。

用户查询：{query}

候选文档片段：
{documents}

请为每个片段评分（0-10分，10分最相关），并返回JSON格式：
{{
  "results": [
    {{"index": 0, "score": 8.5, "reason": "相关原因"}},
    ...
  ]
}}

评分标准：
- 10分：完全回答了用户的问题
- 7-9分：高度相关，包含关键信息
- 4-6分：部分相关
- 1-3分：略微相关
- 0分：完全不相关"""


async def rerank_with_llm(
    query: str,
    documents: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Rerank search results using LLM.

    Args:
        query: User query
        documents: List of document chunks with 'content' field
        top_k: Number of top results to return

    Returns:
        Reranked list of documents with LLM scores
    """
    if not documents:
        return []

    # Format documents for prompt
    doc_text = "\n\n".join([
        f"[文档{i}] {doc.get('content', '')[:500]}"
        for i, doc in enumerate(documents)
    ])

    prompt = RERANK_PROMPT.format(query=query, documents=doc_text)

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
                    "messages": [
                        {"role": "system", "content": "你是一个JSON格式输出专家，只输出JSON，不要其他内容。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1000,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"].strip()

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content)
            scores = result.get("results", [])

            # Apply scores to documents
            reranked = []
            for score_info in scores:
                idx = score_info.get("index", -1)
                if 0 <= idx < len(documents):
                    doc = documents[idx].copy()
                    doc["rerank_score"] = score_info.get("score", 0)
                    doc["rerank_reason"] = score_info.get("reason", "")
                    reranked.append(doc)

            # Sort by rerank score
            reranked.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

            return reranked[:top_k]

    except Exception as e:
        logger.warning(f"LLM rerank failed: {e}")
        # Fallback: return original order
        return documents[:top_k]


def cross_encoder_similarity(
    query: str,
    document: str,
    weights: dict[str, float] | None = None,
) -> float:
    """
    Simple heuristic-based relevance scoring when LLM rerank is not available.
    Uses term overlap and position-based scoring.

    Args:
        query: User query
        document: Document text
        weights: Custom weights for scoring components

    Returns:
        Relevance score between 0 and 1
    """
    if not query or not document:
        return 0.0

    w = weights or {"overlap": 0.4, "position": 0.3, "length": 0.3}

    query_lower = query.lower()
    doc_lower = document.lower()

    # Term overlap score
    query_terms = set(query_lower.split())
    doc_terms = set(doc_lower.split())
    overlap = len(query_terms & doc_terms) / max(len(query_terms), 1)

    # Position score (earlier matches score higher)
    position_score = 1.0
    for i, term in enumerate(query_lower.split()):
        pos = doc_lower.find(term)
        if pos >= 0:
            position_score *= max(0.5, 1.0 - pos / len(doc_lower))

    # Length penalty (prefer medium-length documents)
    len_ratio = len(document) / 1000  # Normalize to ~1000 chars
    length_score = 1.0 / (1.0 + abs(len_ratio - 1.0))

    # Combined score
    score = (
        w["overlap"] * overlap +
        w["position"] * position_score +
        w["length"] * length_score
    )

    return round(min(1.0, max(0.0, score)), 4)


async def rerank_results(
    query: str,
    documents: list[dict[str, Any]],
    top_k: int = 5,
    use_llm: bool = True,
) -> list[dict[str, Any]]:
    """
    Rerank search results.

    Args:
        query: User query
        documents: List of document chunks
        top_k: Number of top results to return
        use_llm: Whether to use LLM for reranking (slower but better)

    Returns:
        Reranked list of documents
    """
    if not documents:
        return []

    # Limit documents sent to LLM to avoid token limits
    docs_to_rerank = documents[:20]

    if use_llm:
        return await rerank_with_llm(query, docs_to_rerank, top_k)
    else:
        # Use heuristic scoring
        for doc in docs_to_rerank:
            doc["rerank_score"] = cross_encoder_similarity(query, doc.get("content", ""))
        docs_to_rerank.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return docs_to_rerank[:top_k]
