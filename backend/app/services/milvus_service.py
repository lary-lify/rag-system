"""
Milvus Service - Vector database collection management.
One collection per knowledge base, with IVF_FLAT index.

IMPORTANT: pymilvus is synchronous. All calls are wrapped in
run_in_executor to avoid blocking the asyncio event loop.

集合加载策略（P0）：
    pymilvus 的 Collection.load() 是一次重量级 RPC——它要把索引段从对象存储
    拉进 QueryNode 内存。原实现每次查询都 load()/release() 一对调用，等于把
    一次向量检索放大成三次跨进程往返，且两次查询之间 Milvus 侧反复换入换出。
    现改为加载后常驻，由 MILVUS_AUTO_RELEASE 控制是否退回旧行为。
"""
from __future__ import annotations

import asyncio
import logging
import threading
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
_pool_lock = threading.Lock()

# 常驻内存的集合句柄：kb_id -> Collection
# pymilvus 的 Collection 只是轻量句柄，真正的状态在服务端，跨线程复用安全。
_loaded: dict[int, Collection] = {}
_loaded_lock = threading.Lock()


def _get_pool():
    """按配置容量惰性创建线程池（双检锁，避免并发首调用重复创建）。"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                import concurrent.futures

                workers = max(1, int(settings.MILVUS_POOL_WORKERS))
                _pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=workers, thread_name_prefix="milvus"
                )
                logger.info(f"[milvus] Thread pool started (workers={workers})")
    return _pool


def shutdown_pool(timeout: float | None = None) -> None:
    """关闭线程池：先等一等在途任务，超时再取消尚未开始的。

    原实现是 shutdown(wait=False)——立刻返回，一个在途任务都不等。但优雅
    关闭窗口（gunicorn --graceful-timeout，默认 30s）本来就是留给在途请求的：
    向量写入是入库流水线的最后一棒，在这一刻被丢掉，会留下「MySQL 里有
    chunk、Milvus 里没有向量」的半截数据，重启后也不会自动补。

    ThreadPoolExecutor.shutdown() 没有 timeout 参数，wait=True 会无限期阻塞。
    所以把阻塞的那个 shutdown 丢到后台线程，主线程只 join 到预算上限：

    - 预算内跑完：等价于 wait=True，数据完整，无副作用
    - 超时：用 cancel_futures 取消队列里尚未开始的任务，已经在执行的任务
      无法中断（Python 没有安全杀线程的手段），只能随进程退出被回收，
      并留下明确告警——这类中断对应的是需要人工补偿的数据，静默吞掉最危险

    预算取自 MILVUS_SHUTDOWN_TIMEOUT，必须小于 gunicorn 的
    --graceful-timeout，否则窗口先被耗尽、进程吃 SIGKILL，等待形同虚设。
    """
    global _pool

    budget = settings.MILVUS_SHUTDOWN_TIMEOUT if timeout is None else float(timeout)

    # 先摘掉全局引用并清句柄缓存：新来的调用不会再往池里投任务，
    # 等待的只是一批有界的存量任务。
    with _pool_lock:
        pool, _pool = _pool, None
    with _loaded_lock:
        _loaded.clear()

    if pool is None:
        return

    if budget <= 0:
        pool.shutdown(wait=False, cancel_futures=True)
        logger.info("[milvus] Thread pool shut down immediately (no wait)")
        return

    waiter = threading.Thread(
        target=pool.shutdown,
        kwargs={"wait": True},
        name="milvus-pool-shutdown",
        daemon=True,
    )
    waiter.start()
    waiter.join(budget)

    if waiter.is_alive():
        # 超时：清掉排队中的任务，免得关停瞬间又拉起一批新的向量写入
        pool.shutdown(wait=False, cancel_futures=True)
        logger.warning(
            f"[milvus] 线程池关闭等待超时（{budget}s），已取消尚未开始的任务；"
            f"正在执行的向量读写将无法完成，可能出现 chunk 已入库而向量缺失，"
            f"需要重新处理对应文档。可调大 MILVUS_SHUTDOWN_TIMEOUT 或排查 "
            f"Milvus 侧延迟。"
        )
    else:
        logger.info("[milvus] Thread pool shut down gracefully (in-flight tasks drained)")


def _forget(kb_id: int) -> None:
    """丢弃缓存的集合句柄（集合被删除/重建，或需要强制释放时调用）。"""
    with _loaded_lock:
        _loaded.pop(kb_id, None)


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
            _forget(kb_id)
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
    loop = asyncio.get_running_loop()
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
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        _get_pool(),
        _insert_vectors_sync, kb_id, chunk_ids, document_ids, contents, vectors, dimension,
    )
    logger.debug(f"[milvus] Inserted {len(chunk_ids)} vectors into KB{kb_id}")


def _get_loaded_collection_sync(kb_id: int) -> Collection | None:
    """
    取一个可用于查询的集合：不存在返回 None；存在则确保其已加载。

    常驻模式下命中缓存后不再发 load() RPC。若服务端因内存压力自行释放了
    集合，search 会抛异常，由 _search_vectors_sync 捕获后重新加载重试。
    """
    name = _col_name(kb_id)
    _connect_sync()

    if not utility.has_collection(name, using=_MILVUS_ALIAS):
        return None

    with _loaded_lock:
        col = _loaded.get(kb_id)

    if col is not None and not settings.MILVUS_AUTO_RELEASE:
        return col  # 已加载且策略为常驻，跳过 load RPC

    if col is None:
        col = Collection(name, using=_MILVUS_ALIAS)
    col.load()
    with _loaded_lock:
        _loaded[kb_id] = col
    return col


def _do_search(col: Collection, query_vector, top_k, threshold) -> list[dict]:
    """对已加载的集合执行一次检索。"""
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
    return hits


def _release_sync(kb_id: int, col: Collection) -> None:
    """仅在 MILVUS_AUTO_RELEASE 开启时释放（兼容旧行为，默认关闭）。"""
    try:
        col.release()
    except Exception as e:  # 释放失败不应影响已经拿到的检索结果
        logger.warning(f"[milvus] release kb_{kb_id} failed: {e}")
    finally:
        _forget(kb_id)


def _search_vectors_sync(kb_id, query_vector, top_k, threshold):
    col = _get_loaded_collection_sync(kb_id)
    if col is None:
        return []
    try:
        return _do_search(col, query_vector, top_k, threshold)
    except Exception as e:
        # 服务端侧集合被释放（内存压力、外部手动 release）时重新加载重试一次
        msg = str(e).lower()
        if "not loaded" not in msg and "code=101" not in msg:
            raise
        logger.warning(f"[milvus] kb_{kb_id} not loaded, reloading and retrying: {e}")
        col.load()
        return _do_search(col, query_vector, top_k, threshold)
    finally:
        if settings.MILVUS_AUTO_RELEASE:
            _release_sync(kb_id, col)


async def search_vectors(kb_id, query_vector, top_k=None, min_score=None):
    k = top_k or settings.RAG_TOP_K
    threshold = min_score if min_score is not None else settings.RAG_SCORE_THRESHOLD
    loop = asyncio.get_running_loop()
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
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        _get_pool(),
        _delete_by_chunk_ids_sync, kb_id, chunk_ids,
    )


def _drop_collection_sync(kb_id):
    name = _col_name(kb_id)
    _connect_sync()
    if utility.has_collection(name, using=_MILVUS_ALIAS):
        utility.drop_collection(name, using=_MILVUS_ALIAS)
    _forget(kb_id)


async def drop_collection(kb_id):
    loop = asyncio.get_running_loop()
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
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _get_pool(),
        _get_stats_sync, kb_id,
    )


async def warmup(kb_ids: list[int]) -> None:
    """
    预加载指定知识库的集合，避免首个真实请求承担加载延迟。

    应用启动后调用，可把冷启动的第一跳延迟从"用户承担"挪到"启动阶段承担"。
    """
    if not kb_ids:
        return
    loop = asyncio.get_running_loop()

    def _warm(kb_id: int) -> None:
        try:
            _get_loaded_collection_sync(kb_id)
        except Exception as e:
            logger.warning(f"[milvus] warmup kb_{kb_id} failed: {e}")

    await asyncio.gather(*[
        loop.run_in_executor(_get_pool(), _warm, kb_id) for kb_id in kb_ids
    ])
    logger.info(f"[milvus] Warmed up {len(kb_ids)} collection(s)")
