"""
Milvus 连接单例（ORM alias 风格，兼容现有 milvus_service.py 使用的 pymilvus.Collection）。

把连接管理集中到 clients 层，避免在每个向量操作里各自 connections.connect。
对外仍通过 get_milvus_connection() 暴露，milvus_service 的内部实现改为调用它。
"""
from __future__ import annotations

import logging

from pymilvus import connections

from app.core.config import settings

logger = logging.getLogger(__name__)

_MILVUS_ALIAS = "rag_kb_default"
_connected = False


class MilvusConnection:
    """pymilvus connections 的轻量单例封装（alias=rag_kb_default）。"""

    def connect(self) -> None:
        global _connected
        if _connected:
            return
        try:
            connections.get_connection(_MILVUS_ALIAS)
            _connected = True
        except Exception:
            connections.connect(
                alias=_MILVUS_ALIAS,
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
            )
            _connected = True
        logger.info(f"Milvus connected (alias={_MILVUS_ALIAS})")

    def disconnect(self) -> None:
        global _connected
        try:
            connections.disconnect(_MILVUS_ALIAS)
        except Exception as e:
            logger.warning(f"Milvus disconnect warning: {e}")
        _connected = False


_connection = MilvusConnection()


def get_milvus_connection() -> MilvusConnection:
    return _connection
