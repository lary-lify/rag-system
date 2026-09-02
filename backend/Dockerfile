FROM python:3.11-slim

WORKDIR /app

# Install system deps for unstructured file parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpoppler-cpp-dev \
    tesseract-ocr \
    libreoffice \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create data directories
RUN mkdir -p /app/data/uploads /app/data/crawls

COPY . .

EXPOSE 8000

# 进程模型
# --------
# 单进程 uvicorn 只能用满一个核，其余核全程空闲，是这套服务最大的一块
# 未利用资源。改用 gunicorn 管理多个 uvicorn worker 进程。
#
# APP_WORKERS 与 config.py 中的同名配置共用同一个环境变量：后者用它推算
# 数据库连接池总占用（db_total_connections），改 worker 数时连接池会同步
# 收敛，不会打穿 MySQL max_connections。
#
# 默认值以 config.py 的 APP_WORKERS 为准（当前 2）。这里和 compose 里的
# 兜底值必须与之相同，否则同一份代码在容器内外会算出不同的连接池预算。
# 启动时后端会打印实际预算，超过 DB_MAX_CONNECTIONS_BUDGET 则告警。
#
# --timeout 0：关闭 gunicorn 的 worker 超时。对话接口是 SSE 长连接，一次
# 生成可能持续数分钟，超时机制会把正在流式输出的进程当成卡死杀掉。
# 代价是失去了对卡死 worker 的兜底，由下面的 HEALTHCHECK 补位：worker
# 真的卡死时 /api/health 会连续失败，由编排层据此重启容器。
#
# --graceful-timeout：滚动重启时给在途请求留出的退出时间。
#
# 注意：worker 数是按进程数放大的，Milvus 线程池（MILVUS_POOL_WORKERS）
# 与进程内缓存同理 —— P0 的缓存是每进程一份，多 worker 下命中率会被摊薄，
# 接 Redis 后统一。
ENV APP_WORKERS=2
ENV APP_GRACEFUL_TIMEOUT=30

CMD ["sh", "-c", "exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers \"${APP_WORKERS:-2}\" \
    --bind 0.0.0.0:8000 \
    --timeout 0 \
    --graceful-timeout \"${APP_GRACEFUL_TIMEOUT:-30}\" \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile -"]
