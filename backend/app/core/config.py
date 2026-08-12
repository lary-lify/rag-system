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
    RAG_TOP_K: int = 5
    RAG_SCORE_THRESHOLD: float = 0.3
    RAG_RETRIEVE_MODE: Literal["vector", "keyword", "mix"] = "mix"  # type: ignore[assignment]

    # ---- SSE streaming ----
    SSE_TIMEOUT_MS: int = 120000

    # ---- Initial super admin ----
    INIT_ADMIN_USERNAME: str = "admin"
    INIT_ADMIN_PASSWORD: str = ""
    INIT_ADMIN_REAL_NAME: str = "超级管理员"
    INIT_ADMIN_EMAIL: str = "admin@rag.local"

    # ---- Derived properties ----
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
