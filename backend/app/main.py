"""
FastAPI application entry point - rag-kb-system.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.cache import configure_caches
from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.limiter import limiter
from app.core.logging_config import setup_logging
from app.clients.http_client import close_http_clients
from app.clients.milvus import get_milvus_connection

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Validate critical security configurations
    if not settings.JWT_SECRET_KEY:
        raise ValueError(
            "JWT_SECRET_KEY is not set. Please configure it in your .env file.\n"
            "Example: JWT_SECRET_KEY=your-random-secret-key-at-least-32-chars"
        )

    # Ensure upload directories exist
    for d in (settings.UPLOAD_DIR, settings.CRAWL_DIR):
        os.makedirs(d, exist_ok=True)

    # 按配置刷新缓存容量与 TTL（缓存实例在导入时用的是代码内默认值）
    configure_caches()

    await init_db()

    # Run database migrations
    try:
        from migrate_embedding_model import migrate as migrate_embedding
        await migrate_embedding()
    except Exception as e:
        logger.warning(f"Embedding model migration skipped: {e}")

    from init_data import create_super_admin
    await create_super_admin()

    logger.info(f"{settings.APP_NAME} started on port {settings.APP_PORT}")
    yield
    # 关闭外部连接（HTTP 连接池 / Milvus）
    await close_http_clients()
    # 释放常驻集合句柄与线程池，再断开连接，避免关闭时出现半释放状态
    try:
        from app.services.milvus_service import shutdown_pool

        shutdown_pool()
    except Exception as e:
        logger.warning(f"Milvus pool shutdown skipped: {e}")
    get_milvus_connection().disconnect()
    await close_db()
    logger.info(f"{settings.APP_NAME} stopped.")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Enterprise RAG Knowledge Base System",
    lifespan=lifespan,
)

# ---- Rate Limiting ----
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---- CORS ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Content-Type-Options", "Content-Disposition"],
)


# ---- Global exception handler ----
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---- Health check ----
@app.get("/api/health")  # 健康检查：探活
async def health_check():
    """
    接口说明：健康检查接口，用于负载均衡/容器探活与监控，无需鉴权。
    方法路径：GET /api/health
    鉴权要求：匿名（公开）
    请求参数：无
    响应字段：{status: "ok", service: 服务名}
    错误码：无
    """
    return {"status": "ok", "service": settings.APP_NAME}


# ---- Register routers ----
from app.api.auth import router as auth_router  # noqa: E402
from app.api.users import router as users_router  # noqa: E402
from app.api.knowledge_bases import router as kb_router  # noqa: E402
from app.api.documents import router as docs_router  # noqa: E402
from app.api.chunks import router as chunks_router  # noqa: E402
from app.api.conversations import router as conv_router  # noqa: E402
from app.api.reports import router as report_router  # noqa: E402
from app.api.audit import router as audit_router  # noqa: E402
from app.api.config_view import router as config_router  # noqa: E402

app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users_router, prefix="/api/users", tags=["Users"])
app.include_router(kb_router, prefix="/api/knowledge-bases", tags=["Knowledge Bases"])
app.include_router(docs_router, prefix="/api/documents", tags=["Documents"])
app.include_router(chunks_router, prefix="/api/chunks", tags=["Chunks"])
app.include_router(conv_router, prefix="/api/conversations", tags=["Conversations"])
app.include_router(report_router, prefix="/api/reports", tags=["Reports"])
app.include_router(audit_router, prefix="/api/audit", tags=["Audit"])
app.include_router(config_router, prefix="/api/config", tags=["Config View"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG,
    )
