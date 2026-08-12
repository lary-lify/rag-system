"""
Hybrid Search Service - BM25 + Vector search with RRF fusion.
Combines keyword-based BM25 search with semantic vector search
for improved retrieval accuracy.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


class BM25:
    """BM25 ranking algorithm for keyword search."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization - split by whitespace and punctuation."""
        import re
        # Split by non-alphanumeric characters, keep Chinese characters
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', text.lower())
        return tokens

    def _idf(self, doc_freq: int, total_docs: int) -> float:
        """Calculate IDF score."""
        return math.log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)

    def score(self, query_tokens: list[str], doc_tokens: list[str],
              doc_freq: dict[str, int], total_docs: int) -> float:
        """Calculate BM25 score for a document."""
        score = 0.0
        doc_len = len(doc_tokens)
        doc_term_count = defaultdict(int)
        for token in doc_tokens:
            doc_term_count[token] += 1

        for query_token in query_tokens:
            if query_token not in doc_term_count:
                continue
            tf = doc_term_count[query_token]
            df = doc_freq.get(query_token, 0)
            idf = self._idf(df, total_docs)
            tf_norm = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / 100))
            score += idf * tf_norm

        return score


async def bm25_search(
    db: AsyncSession,
    kb_id: int,
    query: str,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """
    Perform BM25 keyword search on chunks.
    Returns list of {chunk_id, content, score}.
    """
    import re
    tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', query.lower())
    if not tokens:
        return []

    # Build MySQL FULLTEXT search query
    # Use ngram parser for Chinese support
    search_terms = ' '.join(tokens)

    try:
        # MySQL FULLTEXT search with MATCH...AGAINST
        query_sql = text("""
            SELECT id, content,
                   MATCH(content) AGAINST(:search_term IN NATURAL LANGUAGE MODE) as relevance_score
            FROM chunks
            WHERE kb_id = :kb_id
              AND is_deleted = 0
              AND MATCH(content) AGAINST(:search_term IN NATURAL LANGUAGE MODE)
            ORDER BY relevance_score DESC
            LIMIT :limit
        """)

        result = await db.execute(query_sql, {
            "search_term": search_terms,
            "kb_id": kb_id,
            "limit": top_k,
        })

        rows = result.fetchall()
        return [
            {
                "chunk_id": row[0],
                "content": row[1],
                "score": float(row[2]) if row[2] else 0.0,
                "source": "bm25",
            }
            for row in rows
        ]
    except Exception as e:
        logger.warning(f"BM25 search failed: {e}")
        return []


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    k: int = 60,
) -> list[dict]:
    """
    Reciprocal Rank Fusion (RRF) to combine multiple result lists.

    Args:
        result_lists: List of result lists from different search methods
        k: Constant for RRF formula (default 60)

    Returns:
        Fused and deduplicated results sorted by RRF score
    """
    chunk_scores: dict[int, float] = defaultdict(float)
    chunk_data: dict[int, dict] = {}

    for results in result_lists:
        for rank, result in enumerate(results):
            chunk_id = result.get("chunk_id")
            if chunk_id is None:
                continue

            # RRF formula: 1 / (k + rank)
            rrf_score = 1.0 / (k + rank + 1)
            chunk_scores[chunk_id] += rrf_score

            # Keep the richest data for each chunk
            if chunk_id not in chunk_data or len(result.get("content", "")) > len(chunk_data[chunk_id].get("content", "")):
                chunk_data[chunk_id] = result

    # Sort by combined RRF score
    sorted_chunks = sorted(chunk_scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for chunk_id, score in sorted_chunks:
        if chunk_id in chunk_data:
            result = chunk_data[chunk_id].copy()
            result["rrf_score"] = round(score, 6)
            results.append(result)

    return results


async def hybrid_search(
    db: AsyncSession,
    kb_id: int,
    query: str,
    query_vector: list[float],
    top_k: int | None = None,
    min_score: float | None = None,
    search_mode: str | None = None,
) -> list[dict[str, Any]]:
    """
    Hybrid search combining BM25 and vector search.

    Args:
        db: Database session
        kb_id: Knowledge base ID
        query: Text query for BM25
        query_vector: Embedding vector for semantic search
        top_k: Number of results to return
        min_score: Minimum score threshold
        search_mode: 'vector', 'keyword', or 'mix' (default from config)

    Returns:
        Combined and ranked search results
    """
    from app.services.milvus_service import search_vectors

    k = top_k or settings.RAG_TOP_K
    mode = search_mode or settings.RAG_RETRIEVE_MODE

    # Expand top_k for intermediate results to get better fusion
    intermediate_k = k * 2

    results = []

    if mode == "keyword":
        # BM25 only
        bm25_results = await bm25_search(db, kb_id, query, intermediate_k)
        results = bm25_results[:k]

    elif mode == "vector":
        # Vector search only
        vector_results = await search_vectors(kb_id, query_vector, k, min_score)
        results = vector_results

    else:
        # Hybrid mode: BM25 + Vector with RRF fusion
        bm25_results = await bm25_search(db, kb_id, query, intermediate_k)
        vector_results = await search_vectors(kb_id, query_vector, intermediate_k, min_score)

        if bm25_results or vector_results:
            results = reciprocal_rank_fusion([bm25_results, vector_results])
            results = results[:k]

    # Apply min_score filter if specified
    if min_score is not None:
        score_key = "rrf_score" if mode == "mix" else "score"
        results = [r for r in results if r.get(score_key, 0) >= min_score]

    return results
