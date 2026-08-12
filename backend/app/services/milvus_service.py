"""
Milvus Service - Vector database collection management.
One collection per knowledge base, with IVF_FLAT index.

IMPORTANT: pymilvus is synchronous. All calls are wrapped in
run_in_executor to avoid blocking the asyncio event loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    utility,
)

from app.clients.milvus import get_milvus_connection
from app.core.config import settings

logger = logging.getLogger(__name__)

_MILVUS_ALIAS = "rag_kb_default"

# Thread pool for pymilvus sync operations
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        import concurrent.futures
        _pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="milvus")
    return _pool


def _connect_sync():
    """Ensure Milvus connection is established (via clients.milvus singleton)."""
    get_milvus_connection().connect()


def _col_name(kb_id: int) -> str:
    return f"kb_{kb_id}"


def _ensure_collection_sync(kb_id: int, dimension=None, recreate=False) -> Collection:
    """Synchronous version of ensure_collection — runs in thread pool."""
    dim = dimension or settings.TONGYI_EMBEDDING_DIMENSIONS
    name = _col_name(kb_id)
    _connect_sync()

    if utility.has_collection(name, using=_MILVUS_ALIAS):
        if recreate:
            utility.drop_collection(name, using=_MILVUS_ALIAS)
        else:
            return Collection(name, using=_MILVUS_ALIAS)

    fields = [
        FieldSchema("chunk_id", DataType.INT64, is_primary=True),
        FieldSchema("document_id", DataType.INT64),
        FieldSchema("content", DataType.VARCHAR, max_length=8192),
        FieldSchema("vector", DataType.FLOAT_VECTOR, dim=dim),
    ]

    schema = CollectionSchema(fields=fields, description=f"KB {kb_id} vectors")
    col = Collection(name, schema=schema, using=_MILVUS_ALIAS)

    idx_params = {
        "metric_type": settings.MILVUS_METRIC_TYPE,
        "index_type": settings.MILVUS_INDEX_TYPE,
        "params": {"nlist": settings.MILVUS_NLIST},
    }
    col.create_index(field_name="vector", index_params=idx_params)
    logger.info(f"[milvus] Created collection '{name}' dim={dim}")
    return col


async def ensure_collection(kb_id: int, dimension=None, recreate=False) -> Collection:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _get_pool(),
        _ensure_collection_sync, kb_id, dimension, recreate,
    )


def _insert_vectors_sync(kb_id, chunk_ids, document_ids, contents, vectors, dimension=None):
    col = _ensure_collection_sync(kb_id, dimension=dimension)
    col.insert([chunk_ids, document_ids, contents, vectors])
    col.flush()


async def insert_vectors(kb_id, chunk_ids, document_ids, contents, vectors, dimension=None):
    if not chunk_ids:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _get_pool(),
        _insert_vectors_sync, kb_id, chunk_ids, document_ids, contents, vectors, dimension,
    )
    logger.debug(f"[milvus] Inserted {len(chunk_ids)} vectors into KB{kb_id}")


def _search_vectors_sync(kb_id, query_vector, top_k, threshold):
    name = _col_name(kb_id)
    _connect_sync()

    if not utility.has_collection(name, using=_MILVUS_ALIAS):
        return []

    col = Collection(name, using=_MILVUS_ALIAS)
    col.load()
    results = col.search(
        data=[query_vector],
        anns_field="vector",
        param={"metric_type": settings.MILVUS_METRIC_TYPE, "params": {"nprobe": settings.MILVUS_NPROBE}},
        limit=top_k,
        output_fields=["chunk_id", "document_id", "content"],
    )
    hits = []
    for hit in results[0]:
        if hit.score >= threshold:
            hits.append({
                "chunk_id": hit.entity["chunk_id"],
                "document_id": hit.entity.get("document_id"),
                "content": hit.entity.get("content"),
                "score": round(float(hit.score), 4),
            })
    col.release()
    return hits


async def search_vectors(kb_id, query_vector, top_k=None, min_score=None):
    k = top_k or settings.RAG_TOP_K
    threshold = min_score if min_score is not None else settings.RAG_SCORE_THRESHOLD
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _get_pool(),
        _search_vectors_sync, kb_id, query_vector, k, threshold,
    )


def _delete_by_chunk_ids_sync(kb_id, chunk_ids):
    name = _col_name(kb_id)
    _connect_sync()
    if utility.has_collection(name, using=_MILVUS_ALIAS):
        col = Collection(name, using=_MILVUS_ALIAS)
        col.delete(expr=f"chunk_id in {[int(c) for c in chunk_ids]}")
        col.flush()


async def delete_by_chunk_ids(kb_id, chunk_ids):
    if not chunk_ids:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _get_pool(),
        _delete_by_chunk_ids_sync, kb_id, chunk_ids,
    )


def _drop_collection_sync(kb_id):
    name = _col_name(kb_id)
    _connect_sync()
    if utility.has_collection(name, using=_MILVUS_ALIAS):
        utility.drop_collection(name, using=_MILVUS_ALIAS)


async def drop_collection(kb_id):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _get_pool(),
        _drop_collection_sync, kb_id,
    )
    logger.info(f"[milvus] Dropped collection 'kb_{kb_id}'")


def _get_stats_sync(kb_id) -> dict:
    name = _col_name(kb_id)
    _connect_sync()
    if not utility.has_collection(name, using=_MILVUS_ALIAS):
        return {"exists": False, "row_count": 0}
    col = Collection(name, using=_MILVUS_ALIAS)
    return {"exists": True, "row_count": col.num_entities}


async def get_stats(kb_id) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _get_pool(),
        _get_stats_sync, kb_id,
    )
