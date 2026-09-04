"""
FastAPI application entry point - rag-kb-system.
"""
from __future__ import annotations

import logging
import os
import time
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


def _log_capacity_budget() -> None:
    """
    启动期打印连接池预算，让「worker 数 x 连接池」的放大效应可见。

    MySQL 的 max_connections 是全局的，而连接池是按进程建的：每个 gunicorn
    worker 都会独立持有一份。调大 APP_WORKERS 或调大单 worker 池上限，都会
    成倍放大总连接数。这个乘法不直观，且不设防——超了的表现是运行中随机
   抛 "Too many connections"，排查时很难联想到是 worker 数改过。
    """
    total = settings.db_total_connections
    budget = settings.DB_MAX_CONNECTIONS_BUDGET
    logger.info(
        f"[capacity] workers={settings.APP_WORKERS} "
        f"pool/worker={settings.DB_POOL_SIZE_PER_WORKER}"
        f"+{settings.DB_MAX_OVERFLOW_PER_WORKER} "
        f"-> MySQL connections at full load: {total} (budget {budget})"
    )
    if total > budget:
        logger.warning(
            f"[capacity] 连接池打满时会占用 {total} 个 MySQL 连接，已超过预算 "
            f"{budget}（MySQL max_connections 默认 151）。超限后新请求会随机抛 "
            f"'Too many connections'。请下调 APP_WORKERS / DB_POOL_SIZE_PER_WORKER / "
            f"DB_MAX_OVERFLOW_PER_WORKER，或调高服务端 max_connections 并同步 "
            f"DB_MAX_CONNECTIONS_BUDGET。"
        )


def _cleanup_upload_staging() -> None:
    """启动期回收上次运行遗留的上传临时文件。

    流式上传是先写临时文件、再 os.replace 原子改名到正式目录，正常路径下
    临时文件活不过一次请求。但进程被 kill（OOM、强制重启、容器被 SIGKILL）
    时 finally 根本不执行，文件就留在磁盘上了——既占空间，也在正式文件堆里
    留下一批无法归属的 .upload 文件。

    两条约束缺一不可：

    1. 只扫 .staging 子目录，不碰正式文件目录。作用域封闭，误伤半径可控，
       不会出现「清了个正被引用的正式文档」。
    2. 只清年龄超过 UPLOAD_STAGING_MAX_AGE_SECONDS 的文件。gunicorn 多
       worker 下每个 worker 都会各跑一遍启动逻辑，晚起的 worker 会看到早起
       worker 正在写入的临时文件；不设年龄门槛就会删掉别人的在途上传，
       表现是「偶发上传失败且没有任何报错线索」。门槛取 1 小时，远大于
       单次上传耗时，只回收确定已成垃圾的残留。
    """
    staging = settings.upload_staging_dir
    if not os.path.isdir(staging):
        return

    max_age = max(0, int(settings.UPLOAD_STAGING_MAX_AGE_SECONDS))
    now = time.time()
    removed = 0
    skipped = 0
    freed = 0

    try:
        for name in os.listdir(staging):
            path = os.path.join(staging, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            if not os.path.isfile(path):
                continue
            if now - st.st_mtime < max_age:
                skipped += 1
                continue
            try:
                os.unlink(path)
            except OSError as e:
                logger.warning(f"[upload] 清理暂存残留失败 {path}: {e}")
                continue
            removed += 1
            freed += st.st_size
    except OSError as e:
        logger.warning(f"[upload] 扫描暂存目录失败 {staging}: {e}")
        return

    if removed or skipped:
        logger.info(
            f"[upload] staging cleanup: removed={removed} "
            f"({freed / 1024 / 1024:.1f} MiB), kept_recent={skipped}, dir={staging}"
        )


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
    for d in (settings.UPLOAD_DIR, settings.CRAWL_DIR, settings.upload_staging_dir):
        os.makedirs(d, exist_ok=True)
    # 回收上次异常退出遗留的上传临时文件（只清超过年龄门槛的，避免误删
    # 兄弟 worker 的在途上传）
    _cleanup_upload_staging()

    # 按配置刷新缓存容量与 TTL，并按 CACHE_BACKEND 选择后端（异步：启动期探测 Redis）
    await configure_caches()
    _log_capacity_budget()

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
    # 关闭外部连接（HTTP 连接池 / Milvus / Redis 缓存客户端）
    await close_http_clients()
    try:
        from app.core.cache import close_redis

        close_redis()
    except Exception as e:
        logger.warning(f"Redis client close skipped: {e}")
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
