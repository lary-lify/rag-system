"""
Embedding Service - Alibaba Tongyi text-embedding API integration.
Handles text -> vector conversion with token counting for billing.

P0 改造点：
- 原实现用 for 循环串行请求每一批，批数越多总耗时越长（N 批 = N 次 RTT）。
  现改为多批并发，用信号量把在途请求数限制在 EMBEDDING_MAX_CONCURRENCY。
- 原实现无任何重试，一次网络抖动或上游 429 就会让整批入库失败。
  现对超时、连接错误与 429/5xx 做指数退避重试（带抖动，避免同时重发）。
- 原实现每次都付钱重算。现对已计算过的文本走缓存，命中不再调用 API。
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import AsyncIterator

import httpx

from app.clients.http_client import get_http_client
from app.core.cache import embedding_cache, make_cache_key
from app.core.config import settings

logger = logging.getLogger(__name__)

# 可重试的状态码：限流与服务端错误；4xx 客户端错误重试无意义，直接抛出
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """限制在途批次数，避免一次入库把上游限流打满。"""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, int(settings.EMBEDDING_MAX_CONCURRENCY)))
    return _semaphore


def _cache_key(model_name: str, dim: int, text: str) -> str:
    return make_cache_key(model_name, dim, text)


async def _embed_batch(
    client: httpx.AsyncClient,
    batch: list[str],
    model_name: str,
    dim: int,
) -> tuple[list[list[float]], int]:
    """发起一次批量 embedding 请求，失败按指数退避重试。"""
    max_retries = max(0, int(settings.EMBEDDING_MAX_RETRIES))
    base_delay = max(0.0, float(settings.EMBEDDING_RETRY_BASE_DELAY))

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        async with _get_semaphore():
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
                embeddings = data.get("data", [])
                # 上游不保证返回顺序，按 index 归位后再取向量
                embeddings.sort(key=lambda x: x.get("index", 0))
                vectors = [e["embedding"] for e in embeddings]
                if len(vectors) != len(batch):
                    logger.warning(
                        f"[embedding] batch size mismatch: asked {len(batch)}, got {len(vectors)}"
                    )
                return vectors, usage.get("total_tokens", 0)

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                last_error = e
                if status not in _RETRYABLE_STATUS or attempt >= max_retries:
                    logger.error(
                        f"[embedding] API error {status} (attempt {attempt + 1}/{max_retries + 1}): "
                        f"{e.response.text[:300]}"
                    )
                    raise
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                if attempt >= max_retries:
                    logger.error(f"[embedding] network failure after {attempt + 1} attempt(s): {e}")
                    raise
            except Exception as e:
                # 解析异常等非预期错误不重试，重试也只会得到同样的结果
                logger.error(f"[embedding] unexpected error: {e}")
                raise

        # 退避 + 抖动：同一批请求失败时刻接近，加抖动避免同时重发形成新尖峰
        delay = base_delay * (2 ** attempt) * (0.5 + random.random() * 0.5)
        logger.warning(
            f"[embedding] retry {attempt + 1}/{max_retries} in {delay:.2f}s "
            f"(batch={len(batch)})"
        )
        await asyncio.sleep(delay)

    raise last_error  # type: ignore[misc]


async def embed_texts(
    texts: list[str],
    batch_size: int | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    use_cache: bool = True,
) -> tuple[list[list[float]], int]:
    """
    Embed a list of texts using Tongyi API.

    Args:
        texts: List of text strings to embed
        batch_size: Number of texts per API call (defaults to config)
        model: Embedding model name (defaults to config)
        dimensions: Vector dimensions (defaults to config)
        use_cache: 是否读写缓存。查询侧应开启；批量入库应关闭——入库期
            间涌入的成千上万条片段会把查询向量从 LRU 里挤出去。

    Returns:
        (vectors, total_tokens_used) - vectors in same order as input texts.
        缓存命中不产生 token 消耗。
    """
    if not texts:
        return [], 0

    model_name = model or settings.TONGYI_EMBEDDING_MODEL
    dim = dimensions or settings.TONGYI_EMBEDDING_DIMENSIONS
    size = max(1, int(batch_size or settings.EMBEDDING_BATCH_SIZE))
    cache_on = bool(use_cache and settings.EMBEDDING_CACHE_ENABLED)

    results: list[list[float] | None] = [None] * len(texts)

    # 1) 先过缓存，未命中的按文本去重——重复片段只需计算一次
    unique_texts: dict[str, list[int]] = {}
    for i, text in enumerate(texts):
        if cache_on:
            cached = embedding_cache.get(_cache_key(model_name, dim, text))
            if cached is not None:
                results[i] = cached
                continue
        unique_texts.setdefault(text, []).append(i)

    total_tokens = 0

    if unique_texts:
        uniq_list = list(unique_texts.keys())
        batches = [uniq_list[i : i + size] for i in range(0, len(uniq_list), size)]
        client = get_http_client()

        # 2) 多批并发，在途批次数由信号量收敛
        outputs = await asyncio.gather(*[
            _embed_batch(client, batch, model_name, dim) for batch in batches
        ])

        # 3) 按输入顺序归位
        for batch, (vectors, tokens) in zip(batches, outputs):
            total_tokens += tokens
            for text, vector in zip(batch, vectors):
                if cache_on:
                    embedding_cache.set(_cache_key(model_name, dim, text), vector)
                for i in unique_texts[text]:
                    results[i] = vector

    logger.debug(
        f"[embedding] texts={len(texts)} unique={len(unique_texts)} "
        f"tokens={total_tokens} cache={embedding_cache.stats()['hit_rate']}"
    )

    # 理论上不应存在 None；极端情况下上游少返回时用空向量占位，保持顺序对齐
    return [v if v is not None else [] for v in results], total_tokens


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
