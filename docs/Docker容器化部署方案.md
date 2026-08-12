# RAG知识库系统 - Docker Compose 容器化部署方案

> 版本：v1.0.0 | 更新日期：2026-07-04
>
> **前提：本机裸机跑通、全部功能验证正常后，再使用本文档进行容器化部署。**

---

## 目录

1. [架构设计](#1-架构设计)
2. [前置准备](#2-前置准备)
3. [快速部署](#3-快速部署)
4. [文件清单](#4-文件清单)
5. [容器详解](#5-容器详解)
6. [生产优化建议](#6-生产优化建议)
7. [常用运维命令](#7-常用运维命令)
8. [从裸机迁移到Docker](#8-从裸机迁移到docker)
9. [Docker Compose vs 裸机的关键差异](#9-docker-compose-vs-裸机的关键差异)

---

## 1. 架构设计

### 1.1 容器拓扑

```
                    ┌─────────────────────────┐
                    │    rag-frontend (Nginx)  │
                    │    端口: 80              │
                    │    Vue3 生产构建         │
                    └──────────┬──────────────┘
                               │ /api 反向代理
                               ▼
                    ┌─────────────────────────┐
                    │    rag-backend (FastAPI) │
                    │    端口: 8000            │
                    │    Python 3.11          │
                    └────┬──────────┬─────────┘
                         │          │
                    ┌────▼──┐   ┌──▼───────────────┐
                    │ MySQL │   │ Milvus Standalone │
                    │ 8.0   │   │ 端口: 19530       │
                    │ 3306  │   │                    │
                    └───────┘   └──┬───────┬────────┘
                                   │       │
                              ┌────▼──┐ ┌──▼───┐
                              │ etcd  │ │ MinIO│
                              │ 2379  │ │ 9000 │
                              └───────┘ └──────┘
```

### 1.2 数据持久化

| 数据卷 | 用途 | 挂载位置 |
|--------|------|----------|
| `rag_mysql_data` | MySQL 数据文件 | `/var/lib/mysql` |
| `rag_milvus_data` | Milvus 向量数据 | `/var/lib/milvus` |
| `rag_etcd_data` | Milvus 元数据 | `/etcd` |
| `rag_minio_data` | Milvus 对象存储 | `/minio_data` |
| `rag_upload_data` | 用户上传文件 | `/app/data/uploads` |
| `rag_crawl_data` | 爬虫缓存 | `/app/data/crawls` |

### 1.3 网络

- 所有容器加入 `rag_network`（bridge 模式）
- 容器间通过**服务名**通信（非 localhost）
  - MySQL：`mysql:3306`
  - Milvus：`milvus:19530`
  - Backend：`backend:8000`

---

## 2. 前置准备

### 2.1 安装 Docker 和 Docker Compose

```bash
# 验证安装
docker --version      # Docker 24+
docker compose version  # Docker Compose v2+

# 如未安装：
# Windows/Mac: https://www.docker.com/products/docker-desktop/
# Linux: 参考 https://docs.docker.com/engine/install/
```

### 2.2 配置环境变量

```bash
# 复制 Docker 环境变量模板
cd rag-kb-system
cp .env.docker .env  # 或直接编辑 .env.docker

# ★ 必须修改以下两项为你的真实 API Key
TONGYI_API_KEY=sk-xxxxxxxxxxxxx
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx
```

### 2.3 Docker 资源建议

| 资源 | 最低 | 推荐 |
|------|------|------|
| CPU | 4 核 | 8 核 |
| 内存 | 8 GB | 16 GB |
| 磁盘 | 20 GB | 50 GB+ |

> Docker Desktop 设置路径：Settings → Resources → Advanced

---

## 3. 快速部署

### 3.1 一键启动

```bash
# 在项目根目录执行
cd rag-kb-system

# 使用完整编排文件启动
docker compose -f docker-compose.full.yml --env-file .env.docker up -d

# 查看启动进度
docker compose -f docker-compose.full.yml logs -f
```

启动顺序（自动编排）：
1. etcd → minio (Milvus 依赖)
2. mysql（等待就绪）
3. milvus（等待就绪）
4. backend（等待 MySQL + Milvus 就绪）
5. frontend（等待 backend 就绪）

### 3.2 验证部署

```bash
# 检查所有容器状态
docker compose -f docker-compose.full.yml ps

# 应显示 6 个容器均为 healthy/Up：
#   rag-mysql      Up (healthy)
#   rag-etcd       Up (healthy)
#   rag-minio      Up (healthy)
#   rag-milvus     Up (healthy)
#   rag-backend    Up (healthy)
#   rag-frontend   Up

# 测试健康检查
curl http://localhost:8000/api/health
# {"status":"ok","service":"rag-kb-system"}

# 访问前端
# 浏览器打开 http://localhost
# （如果 FRONTEND_PORT 不是 80，则 http://localhost:端口号）
```

### 3.3 停止服务

```bash
# 停止所有容器（保留数据卷）
docker compose -f docker-compose.full.yml down

# 停止并删除数据卷（清空所有数据！）
docker compose -f docker-compose.full.yml down -v
```

---

## 4. 文件清单

| 文件 | 说明 |
|------|------|
| `docker-compose.full.yml` | 完整四容器 + Milvus 依赖编排 |
| `docker-compose.yml` | 原简化版（仅后端容器） |
| `.env.docker` | Docker 环境变量模板 |
| `backend/Dockerfile` | 后端 Python 镜像 |
| `frontend/Dockerfile` | 前端多阶段构建（Node → Nginx） |
| `frontend/nginx.conf` | Nginx 反向代理配置（关键：SSE 支持） |

### 关键配置：Nginx SSE 支持

`frontend/nginx.conf` 中 API 代理必须设置：

```nginx
location /api/ {
    proxy_pass http://backend:8000/api/;
    proxy_buffering off;    # ★ 关键：关闭缓冲，支持 SSE 流式推送
    proxy_read_timeout 180s; # ★ SSE 长连接超时
    proxy_cache off;
}
```

不关闭 `proxy_buffering` 会导致 SSE 流式对话变成一次性返回全部内容。

---

## 5. 容器详解

### 5.1 MySQL 容器

| 属性 | 值 |
|------|-----|
| 镜像 | `mysql:8.0` |
| 端口 | `3306` |
| 数据库 | `rag_kb`（自动创建） |
| 初始化 | `sql/init.sql` 在首次创建时执行 |
| 数据持久化 | `rag_mysql_data` 卷 |

### 5.2 Milvus 容器组

Milvus Standalone 在 Docker 中运行需要 etcd 和 MinIO 两个依赖：

| 容器 | 镜像 | 端口 | 用途 |
|------|------|------|------|
| `rag-milvus` | `milvusdb/milvus:v2.4.17` | 19530, 9091 | 向量检索主服务 |
| `rag-etcd` | `quay.io/coreos/etcd:v3.5.5` | 2379 | 元数据协调 |
| `rag-minio` | `minio/minio:RELEASE.2023-03-20...` | 9000, 9001 | 对象存储 |

> **注意**：Milvus 启动较慢（首次约 60-120s），后端启动依赖 `milvus` 健康检查通过。

### 5.3 后端容器

| 属性 | 值 |
|------|-----|
| 基础镜像 | `python:3.11-slim` |
| 工作目录 | `/app` |
| 数据目录 | `/app/data/uploads`, `/app/data/crawls` |
| 启动命令 | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |

### 5.4 前端容器

| 属性 | 值 |
|------|-----|
| 构建方式 | 多阶段构建（Node 22 → Nginx 1.27 Alpine） |
| 最终镜像大小 | ~20MB |
| 端口 | 80 |
| Nginx 功能 | 静态文件服务 + API 反向代理 + SSE 支持 |

---

## 6. 生产优化建议

### 6.1 安全加固

```bash
# 1. 修改所有默认密钥
SECRET_KEY=<生成32+字符随机字符串>
JWT_SECRET_KEY=<生成64+字符随机字符串>
MYSQL_PASSWORD=<强密码>
INIT_ADMIN_PASSWORD=<强密码>

# 2. 生成密钥可用：
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 6.2 性能调优

```yaml
# docker-compose.full.yml 中可调整

backend:
  deploy:
    resources:
      limits:
        memory: 4g
        cpus: "2"
      reservations:
        memory: 1g
        cpus: "1"

mysql:
  command:
    - --innodb_buffer_pool_size=512M
    - --max_connections=200
```

### 6.3 生产环境建议

| 优化项 | 建议 |
|--------|------|
| HTTPS | 前端 Nginx 前加 Traefik/Caddy 或使用 certbot 配置 SSL |
| 日志 | 配置 Docker logging driver 为 `json-file` + logrotate |
| 监控 | 集成 Prometheus + Grafana 监控容器资源 |
| 备份 | 定期备份 MySQL 数据卷和上传文件卷 |
| CDN | 将前端静态资源部署到 CDN |
| Milvus | 大规模场景考虑 Milvus Cluster 或 Zilliz Cloud |

### 6.4 数据备份

```bash
# 备份 MySQL
docker exec rag-mysql mysqldump -u root -p$MYSQL_PASSWORD rag_kb > backup_$(date +%Y%m%d).sql

# 备份上传文件
docker run --rm -v rag_upload_data:/data -v $(pwd)/backup:/backup alpine tar czf /backup/uploads_$(date +%Y%m%d).tar.gz -C /data .

# 恢复 MySQL
docker exec -i rag-mysql mysql -u root -p$MYSQL_PASSWORD rag_kb < backup_20260704.sql
```

---

## 7. 常用运维命令

```bash
# 查看所有容器状态
docker compose -f docker-compose.full.yml ps

# 查看实时日志
docker compose -f docker-compose.full.yml logs -f backend
docker compose -f docker-compose.full.yml logs -f milvus
docker compose -f docker-compose.full.yml logs --tail=100

# 进入容器
docker exec -it rag-backend bash
docker exec -it rag-mysql mysql -u root -p

# 重启单个服务
docker compose -f docker-compose.full.yml restart backend
docker compose -f docker-compose.full.yml restart milvus

# 重新构建并启动
docker compose -f docker-compose.full.yml up -d --build

# 查看资源使用
docker stats rag-backend rag-milvus rag-mysql

# 清理未使用的镜像和卷
docker system prune -a
```

---

## 8. 从裸机迁移到 Docker

### 8.1 数据迁移

```bash
# 1. 导出裸机 MySQL 数据
mysqldump -u root -p rag_kb > rag_kb_backup.sql

# 2. 启动 Docker MySQL 后恢复
docker exec -i rag-mysql mysql -u root -p rag_kb < rag_kb_backup.sql

# 3. 复制裸机上传文件
docker run --rm -v rag_upload_data:/data -v ./backend/data/uploads:/source alpine cp -r /source/. /data/
```

### 8.2 环境变量差异

裸机 → Docker 唯一需要修改的：

```bash
# 裸机 .env
MYSQL_HOST=localhost
MILVUS_HOST=localhost

# Docker .env.docker
MYSQL_HOST=mysql       # 容器服务名
MILVUS_HOST=milvus     # 容器服务名
```

---

## 9. Docker Compose vs 裸机的关键差异

| 对比维度 | 裸机部署 | Docker Compose |
|----------|----------|----------------|
| MySQL | 本机安装，`MYSQL_HOST=localhost` | 容器运行，`MYSQL_HOST=mysql` |
| Milvus | 本机 `milvus run standalone`，`MILVUS_HOST=localhost` | 容器运行（含 etcd/minio），`MILVUS_HOST=milvus` |
| 前端 | Vite dev server，端口 5173 | Nginx 生产构建，端口 80 |
| 启动命令 | 4个窗口分步启动 | 一行 `docker compose up -d` |
| 环境隔离 | 依赖本机环境 | 完全隔离的容器环境 |
| 数据持久化 | 本地文件系统 | Docker 数据卷 |
| 迁移性 | 低（依赖系统配置） | 高（docker compose 一键部署） |
| 资源占用 | 按需 | 约 3-6 GB 内存（含 Milvus 依赖） |
| 适用场景 | 开发调试 | 生产部署 / 演示环境 |
| SSE 流式 | 直接连通，无需额外配置 | Nginx 需关闭 `proxy_buffering` |
