"""
共享 HTTP 客户端连接池（单例）。

替换各服务中「每次请求新建 httpx.AsyncClient / httpx.Client」的写法，
复用连接、降低握手开销。连接池在应用关闭时通过 close_http_clients() 释放。

调用方如需覆盖超时，可在 .post(...) 上显式传 timeout= 参数；
也可使用 http_client_context() / sync_http_client_context() 作为 with 上下文，
二者不会在退出时关闭共享连接。
"""
from __future__ import annotations

import httpx
from contextlib import asynccontextmanager, contextmanager

_async_client: httpx.AsyncClient | None = None
_sync_client: httpx.Client | None = None

DEFAULT_TIMEOUT = 120.0


def get_http_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(timeout=httpx.Timeout(DEFAULT_TIMEOUT))
    return _async_client


def get_sync_http_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(timeout=httpx.Timeout(DEFAULT_TIMEOUT))
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
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None
