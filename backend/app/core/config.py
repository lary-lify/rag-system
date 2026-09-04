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

    # ---- Redis (optional, for cache / future rate-limit) ----
    # Redis 连接串。CACHE_BACKEND=redis 时作为共享缓存后端；主请求链路缓存
    # 通过 app.core.cache 的同步客户端接入（与 TTLCache 同接口，调用方零改动）。
    REDIS_URL: str = "redis://localhost:6379/0"
    # 缓存后端：memory=进程内（默认，单机/少 worker 零依赖）；
    # redis=共享缓存（多副本共享、重启不丢，需自备 Redis 服务，compose.full 已含）。
    # 连不上 Redis 时自动降级 memory 并告警，不阻塞启动。
    CACHE_BACKEND: Literal["memory", "redis"] = "redis"  # type: ignore[assignment]

    # ---- 日报定时汇总（内置调度器，可选）----
    # 是否启用内置调度器每日触发 daily_summary 三张表汇总。
    # 关闭后也可由外部 cron 定时调 POST /api/reports/trigger-summary 达到同样效果。
    DAILY_SUMMARY_ENABLED: bool = True
    # 每日触发小时（本地时间 0-23），汇总前一天数据。汇总写入为 ON DUPLICATE KEY UPDATE，
    # 多 worker 重复触发幂等无害，无需分布式锁；服务停机错过触发点时，启动会补跑昨天。
    DAILY_SUMMARY_HOUR: int = 2

    # ---- File Upload ----
    UPLOAD_MAX_SIZE_MB: int = 50
    # 允许的上传扩展名。document_parser 已支持 csv 解析（documents.py 的 csv 分支），
    # 但这里的默认值此前漏了 csv，导致「代码能解析、默认却禁止上传」——只有显式
    # 在 .env 里补上才能用。与代码实际能力对齐。
    UPLOAD_ALLOWED_EXTENSIONS: str = "pdf,docx,doc,pptx,ppt,txt,md,xlsx,xls,csv"
    UPLOAD_DIR: str = "/app/data/uploads"
    CRAWL_DIR: str = "/app/data/crawls"

    # 上传暂存目录名。流式写盘的临时文件不再与正式文件混放在 UPLOAD_DIR
    # 根下，而是单独收进这个子目录：混放时一旦进程被 kill（OOM、强制重启），
    # finally 来不及执行，残骸就是一堆散落在正式文件里的 .upload 文件，
    # 既没法一眼分辨，清理时也要遍历整个 uploads 并靠扩展名猜。
    #
    # 独立子目录带来两个好处：清理逻辑的作用域是确定的（整个目录可删），
    # 且正式文件目录永远干净，备份/同步时不会被临时文件污染。
    UPLOAD_STAGING_SUBDIR: str = ".staging"
    # 启动清理时保留的最小文件年龄（秒）。不设门槛直接清空是有风险的：
    # gunicorn 多 worker 下每个 worker 都会单独执行启动逻辑，晚起的 worker
    # 会看到早起 worker 正在写入的临时文件，直接删掉会让它上传失败。
    # 设一个远大于单次上传耗时的门槛（1 小时），只回收确定已成垃圾的残留。
    UPLOAD_STAGING_MAX_AGE_SECONDS: int = 3600

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
    #
    # 这里是唯一真源：Dockerfile 与 compose 的兜底值必须与此相同，否则同一份
    # 代码在容器内外会算出不同的连接池预算。改这里时要同步改那两处。
    # 本地开发跑单进程 uvicorn 时，在 .env 里显式设 APP_WORKERS=1 覆盖。
    APP_WORKERS: int = 2
    # SQL 回显开关。None 表示跟随 APP_DEBUG；生产环境建议显式设为 False，
    # 否则每条 SQL 都会落日志，高并发下日志 IO 本身就是瓶颈。
    SQL_ECHO: bool | None = None

    # ---- MySQL 连接池 ----
    DB_POOL_SIZE_PER_WORKER: int = 5
    DB_MAX_OVERFLOW_PER_WORKER: int = 10
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True
    # MySQL 侧 max_connections 的预算上限，仅用于启动期核对与告警。
    # MySQL 社区版默认 151，改过服务端配置后同步改这里，否则告警会误报。
    # 留够余量：应用之外还有管理连接、其他服务与备份任务会占用连接。
    DB_MAX_CONNECTIONS_BUDGET: int = 151

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
    # 关闭时等待在途向量读写完成的最长时间（秒）。必须小于 gunicorn 的
    # --graceful-timeout（默认 30s），否则优雅关闭窗口会先被耗尽，进程被
    # SIGKILL，等待逻辑形同虚设。留 10s 余量给 HTTP 连接池与 DB 关闭。
    MILVUS_SHUTDOWN_TIMEOUT: float = 20.0

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
    # 改写是挡在检索之前的同步等待，这里的每一秒都会原样叠加到用户感知的
    # 首字延迟上（命中缓存时则完全不耗时）。8s 意味着一次外部 API 抖动就能
    # 让对话开头卡住近 10 秒，而改写的收益（召回略微变好）远不值这个代价。
    #
    # 取 3s 的理由：正常一次改写是几百毫秒，3s 已经是很宽松的上限；超时后
    # 链路会降级用原始 query 继续检索，功能不受影响——这是「宁可少改写，
    # 不可让用户干等」的取舍。要更激进可以调到 2s。
    #
    # 注意与 HTTP_READ_TIMEOUT（60s）的分工：后者是单次 HTTP 读超时兜底，
    # 这里是对整个改写调用的业务级预算，两者取先到者生效。
    QUERY_REWRITE_TIMEOUT: float = 3.0

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
    def upload_staging_dir(self) -> str:
        """上传临时文件的暂存目录（UPLOAD_DIR 下的子目录，同文件系统）。

        放在 UPLOAD_DIR 内部而不是独立的 /tmp，是因为落盘后要用 os.replace
        原子改名到正式目录——跨文件系统时 os.replace 会抛 OSError，反而丢掉
        原子性保证。
        """
        return os.path.join(self.UPLOAD_DIR, self.UPLOAD_STAGING_SUBDIR)

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
