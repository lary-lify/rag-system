"""
Config View API: Read-only display of current system configuration.
No edit endpoints - all values from environment variables.
"""
from fastapi import APIRouter, Depends
from app.core.cache import all_caches
from app.core.dependencies import require_dept_admin_or_above
from app.models.user import User
from app.schemas.common import CacheStatsResponse, ConfigViewResponse
from app.core.config import settings

router = APIRouter()


@router.get("", response_model=ConfigViewResponse)  # 系统配置只读查看：敏感项打码
async def get_config_view(
    _user: User = Depends(require_dept_admin_or_above()),
):
    """
    接口说明：以只读键值对形式返回当前系统配置（来自环境变量），敏感字段（API Key/密码）已打码为 **** 脱敏展示。
    方法路径：GET /api/config
    鉴权要求：部门管理员及以上
    请求参数：无
    响应字段：ConfigViewResponse{config_items[{key,value,description}]}
    错误码：401 未登录; 403 权限不足
    备注：本接口仅只读展示，不提供任何修改配置的写接口。
    """
    config_items = [
        # ---- Application ----
        {"key": "APP_NAME", "value": settings.APP_NAME, "description": "System name"},
        {"key": "APP_ENV", "value": settings.APP_ENV, "description": "Environment (development/production)"},
        {"key": "APP_PORT", "value": str(settings.APP_PORT), "description": "Backend service port"},
        {"key": "JWT_EXPIRE_HOURS", "value": str(settings.JWT_EXPIRE_HOURS), "description": "Token validity in hours"},

        # ---- Database ----
        {"key": "MYSQL_HOST", "value": settings.MYSQL_HOST, "description": "MySQL host address"},
        {"key": "MYSQL_PORT", "value": str(settings.MYSQL_PORT), "description": "MySQL port"},
        {"key": "MYSQL_DATABASE", "value": settings.MYSQL_DATABASE, "description": "Database name"},
        {"key": "MYSQL_USER", "value": settings.MYSQL_USER, "description": "MySQL username"},

        # ---- Milvus ----
        {"key": "MILVUS_HOST", "value": settings.MILVUS_HOST, "description": "Milvus host address"},
        {"key": "MILVUS_PORT", "value": str(settings.MILVUS_PORT), "description": "Milvus port"},
        {"key": "MILVUS_INDEX_TYPE", "value": settings.MILVUS_INDEX_TYPE, "description": "Vector index type"},
        {"key": "MILVUS_METRIC_TYPE", "value": settings.MILVUS_METRIC_TYPE, "description": "Similarity metric"},
        {"key": "RAG_TOP_K", "value": str(settings.RAG_TOP_K), "description": "Top-K retrieved chunks"},
        {"key": "RAG_SCORE_THRESHOLD", "value": str(settings.RAG_SCORE_THRESHOLD), "description": "Min similarity score"},
        {"key": "RAG_RETRIEVE_MODE", "value": settings.RAG_RETRIEVE_MODE, "description": "Retrieval mode (vector/keyword/mix)"},

        # ---- Tongyi Embedding (masked) ----
        {"key": "TONGYI_API_KEY", "value": _mask_key(settings.TONGYI_API_KEY), "description": "Tongyi API Key"},
        {"key": "TONGYI_EMBEDDING_MODEL", "value": settings.TONGYI_EMBEDDING_MODEL, "description": "Embedding model name"},
        {"key": "TONGYI_EMBEDDING_DIMENSIONS", "value": str(settings.TONGYI_EMBEDDING_DIMENSIONS), "description": "Embedding vector dimensions"},
        {"key": "TONGYI_EMBEDDING_TOKEN_PRICE", "value": str(settings.TONGYI_EMBEDDING_TOKEN_PRICE), "description": "Embedding per-token price (CNY)"},

        # ---- DeepSeek Chat (masked) ----
        {"key": "DEEPSEEK_API_KEY", "value": _mask_key(settings.DEEPSEEK_API_KEY), "description": "DeepSeek API Key"},
        {"key": "DEEPSEEK_CHAT_MODEL", "value": settings.DEEPSEEK_CHAT_MODEL, "description": "Chat LLM model name"},
        {"key": "DEEPSEEK_INPUT_TOKEN_PRICE", "value": str(settings.DEEPSEEK_INPUT_TOKEN_PRICE), "description": "Chat input token price (CNY)"},
        {"key": "DEEPSEEK_OUTPUT_TOKEN_PRICE", "value": str(settings.DEEPSEEK_OUTPUT_TOKEN_PRICE), "description": "Chat output token price (CNY)"},

        # ---- File Upload ----
        {"key": "UPLOAD_MAX_SIZE_MB", "value": str(settings.UPLOAD_MAX_SIZE_MB), "description": "Max upload file size (MB)"},
        {"key": "UPLOAD_ALLOWED_EXTENSIONS", "value": ",".join(settings.upload_allowed_extensions), "description": "Allowed file extensions"},

        # ---- Chunking defaults ----
        {"key": "DEFAULT_CHUNK_STRATEGY", "value": settings.DEFAULT_CHUNK_STRATEGY, "description": "Default chunking strategy"},
        {"key": "DEFAULT_CHUNK_SIZE", "value": str(settings.DEFAULT_CHUNK_SIZE), "description": "Default chunk size (tokens)"},
        {"key": "DEFAULT_CHUNK_OVERLAP", "value": str(settings.DEFAULT_CHUNK_OVERLAP), "description": "Default overlap size (tokens)"},

        # ---- Initial admin ----
        {"key": "INIT_ADMIN_USERNAME", "value": settings.INIT_ADMIN_USERNAME, "description": "Initial super admin username"},
    ]

    return ConfigViewResponse(config_items=config_items)


@router.get("/cache-stats", response_model=CacheStatsResponse)  # 缓存运行统计：命中率与容量水位
async def get_cache_stats(
    _user: User = Depends(require_dept_admin_or_above()),
):
    """
    接口说明：返回进程内缓存（查询向量 / 查询改写）的运行统计，含命中率、容量水位与淘汰计数，用于判断缓存容量是否配够、以及是否需要演进到共享缓存。
    方法路径：GET /api/config/cache-stats
    鉴权要求：部门管理员及以上
    请求参数：无
    响应字段：CacheStatsResponse{caches[{name,size,max_size,ttl,hits,misses,computations,evictions,expirations,hit_rate,utilization,worker_count}],process_note}
    错误码：401 未登录; 403 权限不足
    备注：读数是「当前进程」视角。多 worker 部署时每个 worker 各持一份缓存与一份统计，请求被随机分到其中任意一个，单进程读数只是全局流量的 1/N 采样。
         判读要点：utilization 长期贴着 1 说明工作集装不下、淘汰在持续发生，应调大容量而非调 TTL；hit_rate 偏低而 evictions 偏高是典型容量不足信号。
    """
    stats = []
    for cache in all_caches():
        stat = cache.stats()
        # 把进程数带出去：换算全局量级时要用，否则容易拿单进程读数当全貌
        stat["worker_count"] = max(1, int(settings.APP_WORKERS))
        stats.append(stat)

    return CacheStatsResponse(
        caches=stats,
        process_note=(
            "读数为当前进程视角；多 worker 部署时每个 worker 一份缓存与一份统计，"
            "单进程读数只是全局流量的 1/N 采样，需逐 worker 采集后汇总。"
        ),
    )


def _mask_key(value: str) -> str:
    """Mask sensitive keys: show first 4 + last 2 chars."""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-2:]
