"""
Async MySQL connection management via SQLAlchemy + aiomysql.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---- Async engine & session factory ----
engine = create_async_engine(
    settings.mysql_url + "?charset=utf8mb4",
    echo=settings.APP_DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300,
    pool_pre_ping=False,
)


# Set session timezone to +08:00 (China Standard Time) on each new connection
from sqlalchemy import event, text

@event.listens_for(engine.sync_engine, "connect")
def set_timezone(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("SET time_zone = '+08:00'")
    cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables (for dev / first-run)."""
    from app.models.user import User  # noqa: F401
    from app.models.knowledge_base import KnowledgeBase  # noqa: F401
    from app.models.document import Document  # noqa: F401
    from app.models.chunk import Chunk  # noqa: F401
    from app.models.conversation import Conversation  # noqa: F401
    from app.models.message import Message  # noqa: F401
    from app.models.token_usage import TokenUsage  # noqa: F401
    from app.models.login_log import LoginLog  # noqa: F401
    from app.models.audit_log import AuditLog  # noqa: F401
    from app.models.kb_permission import KBPermission  # noqa: F401

    # 获取数据库中已存在的表名
    async with engine.begin() as conn:
        result = await conn.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE()"
        )
        existing_tables = {row[0] for row in result.fetchall()}

        # 只创建不存在的表（避免与已有表结构冲突）
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                table.create(bind=conn.sync_connection, checkfirst=True)
                logger.info(f"Created table: {table.name}")

        if not existing_tables:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created.")
        else:
            logger.info("Database tables verified.")

    # Migration: ensure token_usage.type supports 'chunking' enum value
    async with engine.begin() as conn:
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE token_usage MODIFY COLUMN type "
                "ENUM('embedding','chat','chunking') NOT NULL"
            )
            logger.info("token_usage.type column migrated (chunking added).")
        except Exception:
            pass  # column already has the new value or table doesn't exist yet

    # Migration: ensure documents.chunk_count has default 0 (missing from initial schema)
    async with engine.begin() as conn:
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE documents MODIFY COLUMN chunk_count INT NOT NULL DEFAULT 0"
            )
            logger.info("documents.chunk_count column migrated (DEFAULT 0 added).")
        except Exception:
            pass

    logger.info("Database tables created/verified.")


async def close_db() -> None:
    """Dispose engine on shutdown."""
    await engine.dispose()
    logger.info("Database engine disposed.")
