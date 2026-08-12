"""
Embedding Service - Alibaba Tongyi text-embedding API integration.
Handles text -> vector conversion with token counting for billing.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx
from app.clients.http_client import http_client_context

from app.core.config import settings

logger = logging.getLogger(__name__)


async def embed_texts(
    texts: list[str],
    batch_size: int = 10,
    model: str | None = None,
    dimensions: int | None = None,
) -> tuple[list[list[float]], int]:
    """
    Embed a list of texts using Tongyi API.

    Args:
        texts: List of text strings to embed
        batch_size: Number of texts per API call
        model: Embedding model name (defaults to config)
        dimensions: Vector dimensions (defaults to config)

    Returns:
        (vectors, total_tokens_used) - vectors in same order as input texts.
    """
    if not texts:
        return [], 0

    model_name = model or settings.TONGYI_EMBEDDING_MODEL
    dim = dimensions or settings.TONGYI_EMBEDDING_DIMENSIONS

    all_vectors = []
    total_tokens = 0

    async with http_client_context() as client:
        # Process in batches to avoid API limits
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                response = await client.post(
                    f"{settings.TONGYI_BASE_URL}/embeddings",
                    headers={
                        "Authorization": f"Bearer {settings.TONGYI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "input": batch,
                        "dimensions": dim,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                usage = data.get("usage", {})
                total_tokens += usage.get("total_tokens", 0)

                embeddings = data.get("data", [])
                # Sort by index to maintain order
                embeddings.sort(key=lambda x: x.get("index", 0))
                all_vectors.extend([e["embedding"] for e in embeddings])

            except httpx.HTTPStatusError as e:
                logger.error(f"Tongyi embedding API error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Unexpected embedding error: {e}")
                raise

    return all_vectors, total_tokens


async def embed_single_text(
    text: str,
    model: str | None = None,
    dimensions: int | None = None,
) -> tuple[list[float], int]:
    """Convenience wrapper for single-text embedding."""
    vectors, tokens = await embed_texts([text], model=model, dimensions=dimensions)
    return (vectors[0] if vectors else []), tokens


# ---- Token counting helpers ----

def estimate_token_count(text: str) -> int:
    """Rough token estimation: Chinese chars ~1.5 tokens, English words ~1 token."""
    import re
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return int(chinese_chars * 1.5 + english_words)
