"""
Global configuration - typed settings sourced from environment variables.

Uses pydantic-settings for type coercion + validation.
IMPORTANT: all env var NAMES are kept identical to the previous os.getenv-based
config, so existing .env files keep working without changes.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from dotenv import load_dotenv

from app.utils.path_utils import find_project_root

# Load .env into os.environ for any code still using os.getenv directly (back-compat).
_env_path = find_project_root() / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_env_path) if _env_path.exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    APP_NAME: str = "rag-kb-system"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-change-me"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # ---- JWT ----
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # ---- MySQL ----
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "rag_kb"

    # ---- Milvus Vector DB ----
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_INDEX_TYPE: str = "IVF_FLAT"
    MILVUS_METRIC_TYPE: str = "COSINE"
    MILVUS_NLIST: int = 1024
    MILVUS_NPROBE: int = 16

    # ---- Alibaba Tongyi Embedding API ----
    TONGYI_API_KEY: str = ""
    TONGYI_EMBEDDING_MODEL: str = "text-embedding-v3"
    TONGYI_EMBEDDING_DIMENSIONS: int = 1024
    TONGYI_EMBEDDING_TOKEN_PRICE: float = 0.0008
    TONGYI_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ---- DeepSeek LLM Chat API ----
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_CHAT_MODEL: str = "deepseek-chat"
    DEEPSEEK_INPUT_TOKEN_PRICE: float = 0.0010
    DEEPSEEK_OUTPUT_TOKEN_PRICE: float = 0.0020
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"

    # ---- Redis (optional, for future rate-limit/cache) ----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- File Upload ----
    UPLOAD_MAX_SIZE_MB: int = 50
    UPLOAD_ALLOWED_EXTENSIONS: str = "pdf,docx,doc,pptx,ppt,txt,md,xlsx,xls"
    UPLOAD_DIR: str = "/app/data/uploads"
    CRAWL_DIR: str = "/app/data/crawls"

    # ---- Chunking defaults ----
    DEFAULT_CHUNK_STRATEGY: str = "fixed_token"
    DEFAULT_CHUNK_SIZE: int = 512
    DEFAULT_CHUNK_OVERLAP: int = 128

    # ---- RAG retrieval ----
    # RAG_TOP_K 是每个知识库各自的召回上限，也是「最终喂给 LLM 的片段数」的
    # 默认上限。跨 N 个知识库检索时，各库各召回 RAG_TOP_K 条，合并后最多
    # RAG_TOP_K x N 条——全部进 prompt 会稀释注意力（lost-in-the-middle）
    # 并推高 cost，因此合并后还要再做一次全局截断。
    RAG_TOP_K: int = 5
    # 合并后全局保留的片段数上限。<=0 表示不截断（保留旧行为）。
    RAG_GLOBAL_TOP_K: int = 5
    RAG_SCORE_THRESHOLD: float = 0.3
    RAG_RETRIEVE_MODE: Literal["vector", "keyword", "mix"] = "mix"  # type: ignore[assignment]

    # ---- Deployment / 进程模型 ----
    # gunicorn worker 数。连接池容量按 worker 数推算，多副本部署时必须与实际一致，
    # 否则会放大 MySQL 连接数（worker 数 x 单 worker 池上限）。
    APP_WORKERS: int = 1
    # SQL 回显开关。None 表示跟随 APP_DEBUG；生产环境建议显式设为 False，
    # 否则每条 SQL 都会落日志，高并发下日志 IO 本身就是瓶颈。
    SQL_ECHO: bool | None = None

    # ---- MySQL 连接池 ----
    DB_POOL_SIZE_PER_WORKER: int = 5
    DB_MAX_OVERFLOW_PER_WORKER: int = 10
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True

    # ---- 共享 HTTP 连接池（DeepSeek / Tongyi 等外部 API） ----
    HTTP_MAX_CONNECTIONS: int = 200
    HTTP_MAX_KEEPALIVE: int = 50
    HTTP_KEEPALIVE_EXPIRY: float = 30.0
    HTTP_CONNECT_TIMEOUT: float = 5.0
    HTTP_READ_TIMEOUT: float = 60.0

    # ---- Milvus ----
    # pymilvus 是同步客户端，调用统一丢线程池，池大小直接决定向量读写并发上限。
    MILVUS_POOL_WORKERS: int = 8
    # 查询后是否释放集合。默认 False：集合加载后常驻，避免每次查询重复 load。
    MILVUS_AUTO_RELEASE: bool = False

    # ---- Embedding 调用 ----
    EMBEDDING_BATCH_SIZE: int = 16
    EMBEDDING_MAX_CONCURRENCY: int = 4
    EMBEDDING_MAX_RETRIES: int = 3
    EMBEDDING_RETRY_BASE_DELAY: float = 1.0
    EMBEDDING_CACHE_ENABLED: bool = True
    EMBEDDING_CACHE_TTL: int = 86400
    # 缓存的是 1024 维向量，单条约 32KB（Python float 列表），
    # 1000 条约 32MB/进程。多 worker 部署时需按 worker 数折算内存。
    EMBEDDING_CACHE_MAX_SIZE: int = 1000

    # ---- 查询改写 ----
    QUERY_REWRITE_ENABLED: bool = True
    QUERY_REWRITE_CACHE_ENABLED: bool = True
    QUERY_REWRITE_CACHE_TTL: int = 3600
    QUERY_REWRITE_CACHE_MAX_SIZE: int = 2000
    QUERY_REWRITE_TIMEOUT: float = 8.0

    # ---- SSE streaming ----
    SSE_TIMEOUT_MS: int = 120000

    # ---- Initial super admin ----
    INIT_ADMIN_USERNAME: str = "admin"
    INIT_ADMIN_PASSWORD: str = ""
    INIT_ADMIN_REAL_NAME: str = "超级管理员"
    INIT_ADMIN_EMAIL: str = "admin@rag.local"

    # ---- Derived properties ----
    @property
    def sql_echo(self) -> bool:
        """SQLAlchemy 是否回显 SQL。未显式配置 SQL_ECHO 时跟随 APP_DEBUG。"""
        return self.APP_DEBUG if self.SQL_ECHO is None else self.SQL_ECHO

    @property
    def db_pool_size(self) -> int:
        """单进程常驻连接数。"""
        return self.DB_POOL_SIZE_PER_WORKER

    @property
    def db_max_overflow(self) -> int:
        """单进程可临时超借的连接数。"""
        return self.DB_MAX_OVERFLOW_PER_WORKER

    @property
    def db_total_connections(self) -> int:
        """进程池打满时占用的 MySQL 连接总数，用于核对 max_connections 是否够用。"""
        return self.APP_WORKERS * (self.DB_POOL_SIZE_PER_WORKER + self.DB_MAX_OVERFLOW_PER_WORKER)

    @property
    def mysql_url(self) -> str:
        """Async SQLAlchemy connection URL for MySQL."""
        pwd = f":{self.MYSQL_PASSWORD}" if self.MYSQL_PASSWORD else ""
        return f"mysql+aiomysql://{self.MYSQL_USER}{pwd}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"

    @property
    def mysql_url_sync(self) -> str:
        """Sync SQLAlchemy connection URL (for migrations/initialization)."""
        pwd = f":{self.MYSQL_PASSWORD}" if self.MYSQL_PASSWORD else ""
        return f"mysql+pymysql://{self.MYSQL_USER}{pwd}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"

    @property
    def upload_max_bytes(self) -> int:
        return self.UPLOAD_MAX_SIZE_MB * 1024 * 1024

    @property
    def upload_allowed_extensions(self) -> list[str]:
        return [x.strip() for x in self.UPLOAD_ALLOWED_EXTENSIONS.split(",") if x.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def SUPPORTED_EMBEDDING_MODELS(self) -> dict[str, int]:
        """Supported embedding models -> vector dimension (hardcoded, not from env)."""
        return {
            "text-embedding-v3": 1024,
            "text-embedding-v2": 1024,
            "text-embedding-v1": 1024,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()


settings = get_settings()
