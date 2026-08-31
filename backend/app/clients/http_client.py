"""
共享 HTTP 客户端连接池（单例）。

替换各服务中「每次请求新建 httpx.AsyncClient / httpx.Client」的写法，
复用连接、降低握手开销。连接池在应用关闭时通过 close_http_clients() 释放。

调用方如需覆盖超时，可在 .post(...) 上显式传 timeout= 参数；
也可使用 http_client_context() / sync_http_client_context() 作为 with 上下文，
二者不会在退出时关闭共享连接。
"""
from __future__ import annotations

import threading

import httpx
from contextlib import asynccontextmanager, contextmanager

from app.core.config import settings

_async_client: httpx.AsyncClient | None = None
_sync_client: httpx.Client | None = None
# 构造客户端的过程没有 await 点，用同步锁即可避免并发首次调用时重复构造。
_client_lock = threading.Lock()

DEFAULT_TIMEOUT = 120.0


def _build_timeout() -> httpx.Timeout:
    """分级超时。

    建连和从池里取连接应当快速失败，避免一个不可达的上游把请求全挂住；
    读响应按模型生成耗时给足时间，具体接口仍可在调用处覆盖。
    """
    return httpx.Timeout(
        connect=settings.HTTP_CONNECT_TIMEOUT,
        read=settings.HTTP_READ_TIMEOUT,
        write=settings.HTTP_READ_TIMEOUT,
        pool=settings.HTTP_CONNECT_TIMEOUT,
    )


def _build_limits() -> httpx.Limits:
    """按并发目标显式配置池容量。

    httpx 默认是 max_connections=100 / max_keepalive=20，对 LLM 与 Embedding
    这类长耗时外部调用来说，超出的请求会在池边静默排队，表现为延迟无端升高。
    """
    return httpx.Limits(
        max_connections=settings.HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE,
        keepalive_expiry=settings.HTTP_KEEPALIVE_EXPIRY,
    )


def get_http_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        with _client_lock:
            if _async_client is None:
                _async_client = httpx.AsyncClient(
                    timeout=_build_timeout(),
                    limits=_build_limits(),
                )
    return _async_client


def get_sync_http_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        with _client_lock:
            if _sync_client is None:
                _sync_client = httpx.Client(
                    timeout=_build_timeout(),
                    limits=_build_limits(),
                )
    return _sync_client


@asynccontextmanager
async def http_client_context():
    """返回共享异步客户端；退出时不关闭（连接池由 close_http_clients 统一回收）。"""
    yield get_http_client()


@contextmanager
def sync_http_client_context():
    """返回共享同步客户端；退出时不关闭。"""
    yield get_sync_http_client()


async def close_http_clients() -> None:
    global _async_client, _sync_client
    with _client_lock:
        client, _async_client = _async_client, None
        sync_client, _sync_client = _sync_client, None
    if client is not None:
        await client.aclose()
    if sync_client is not None:
        sync_client.close()
