# 企业级 RAG 知识库系统 (rag-system)

> 面向企业的检索增强生成（RAG）知识库平台，支持多租户权限、多策略文档切片、向量 + 关键词混合召回、SSE 流式对话与全链路审计。

## 功能特性

### 权限与租户
- **三级权限模型**：超级管理员 / 部门管理员 / 普通用户
- **知识库隔离模式**：私有知识库、共享知识库
- **细粒度权限控制**：`read` / `upload` / `admin` 三级知识库权限（`kb_permissions` 表）
- **JWT 登录认证**：Access Token + 密码哈希，超管账号通过环境变量初始化
- **审计日志**：记录用户关键操作，支持按时间/用户/操作类型筛选与 CSV 导出

### 文档与知识库管理
- **知识库 CRUD**：创建、编辑、删除、列表、权限配置
- **文档上传**：支持 `pdf` / `docx` / `doc` / `pptx` / `ppt` / `txt` / `md` / `xlsx` / `xls` / `csv` 格式上传，存储于 `data/uploads/`
- **文档解析**：自动提取文本内容并生成文档记录
- **七种切片策略**：
  - 固定 Token（fixed_token）
  - 语义切片（semantic）
  - 段落切片（paragraph）
  - 标题层级切片（heading_level）
  - 问答对切片（qa_pair）
  - 递归切片（recursive）
  - AI 辅助切片（ai_assisted）
- **切片管理**：查看、删除、重新生成切片

### 检索与对话
- **向量检索**：基于 Milvus + 阿里通义 `text-embedding-v3`
- **混合召回**：向量相似度 + 关键词匹配（hybrid_search）
- **SSE 流式对话**：前端 EventSource 实时渲染，支持停止生成
- **多轮对话**：会话（conversation）与消息（message）持久化
- **引用溯源**：返回召回 chunk 来源，便于核对答案依据

### 计费与报表
- **Token 用量记录**：按用户/会话/模型多维度记录 `input` / `output` / `total`
- **用量汇总**：由 `app/services/daily_summary.py` 写入三张按日汇总表 `daily_token_summary`（Token/费用/请求数）、`daily_qa_summary`（问答统计）、`daily_hot_questions`（热门问题）。内置调度器默认启用（`DAILY_SUMMARY_ENABLED=true`），每日本地时间 `DAILY_SUMMARY_HOUR`（默认 2 点）汇总前一天；写入为 `ON DUPLICATE KEY UPDATE` 幂等，多 worker 重复触发无害。也可关闭内置调度器、由超管调用 `POST /api/reports/trigger-summary` 或外部 cron 手动触发
- **报表与导出**：对话记录导出 Excel，含 Token 明细

### 系统管理
- **系统配置（只读）**：通过 `GET /api/config` 查看嵌入模型、LLM、限额等运行时参数与 `GET /api/config/cache-stats` 查看缓存命中率（部门管理员及以上）；参数调整需修改环境变量后重启，不支持运行时在线改写
- **用户管理**：用户增删改查、角色分配
- **看板/仪表盘**：数据概览与可视化（ECharts）
- **限流与日志**：请求限流、结构化日志按天轮转

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + Ant Design Vue + ECharts |
| 后端 | Python 3.11+ + FastAPI + SQLAlchemy + Pydantic |
| 向量库 | Milvus Standalone |
| 关系库 | MySQL 8.0 |
| 缓存 | Redis（共享缓存后端，按 `CACHE_BACKEND` 在 `memory` / `redis` 间切换；`CACHE_BACKEND=memory` 时为进程内缓存，多 worker 不共享） |
| 嵌入模型 | 阿里通义 `text-embedding-v3` |
| 对话 LLM | DeepSeek (`deepseek-chat`) |
| 部署 | Docker + Docker Compose |

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                          │
│  登录 │ 知识库 │ 文档 │ 对话 │ 报表 │ 审计 │ 用户 │ 配置        │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────────┐
│                      FastAPI 后端                            │
│  auth │ users │ knowledge_bases │ documents │ chunks        │
│  conversations │ reports │ audit │ config_view              │
│  ─────────────────────────────────────────────              │
│  services: hybrid_search │ embedding │ document_parser      │
│           export │ daily_summary                            │
│  ─────────────────────────────────────────────              │
│  clients: http_client │ milvus │ redis                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
     MySQL 8.0        Milvus 2.x           Redis
```

## 目录结构

```
rag-kb-system/
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── api/              # RESTful API 路由（9 个业务模块）
│   │   ├── clients/          # 外部客户端（Milvus / Redis / HTTP）
│   │   ├── core/             # 配置 / 数据库 / 安全 / 日志 / 限流
│   │   ├── models/           # SQLAlchemy 数据模型
│   │   ├── schemas/          # Pydantic 校验模型
│   │   ├── services/         # 业务逻辑（检索 / 嵌入 / 解析 / 导出）
│   │   │   └── chunking/     # 切片策略实现
│   │   ├── utils/            # 工具函数
│   │   └── main.py           # 应用入口
│   ├── tests/                # 测试用例
│   ├── data/                 # 运行时数据（已忽略，保留 .gitkeep）
│   ├── outputs/              # 运行时产物（导出/图表等，已忽略）
│   ├── logs/                 # 运行日志（已忽略）
│   └── requirements.txt      # Python 依赖
├── frontend/                 # Vue 3 前端
│   └── src/
│       ├── views/            # 业务页面
│       ├── components/       # 公共组件
│       ├── api/              # 后端接口封装
│       ├── router/           # 路由配置
│       └── stores/           # Pinia 状态管理
├── sql/                      # 数据库初始化与迁移脚本
├── scripts/                  # 运维脚本（run_*.sh/bat 等）
├── docs/                     # 设计文档
├── samples/                  # 示例文档与素材
├── design-prototype/         # 前端设计原型
├── docker-compose.yml        # 最小部署（仅 rag-backend 单服务，便于本地快速起后端）
├── docker-compose.full.yml   # 完整生产部署（MySQL + Milvus + etcd + MinIO + Redis + 后端 + 前端）
├── .env.example              # 环境变量模板（脚本生成，与 config.py 默认对齐）
├── .env.template             # 环境变量模板（备用）
├── .env.docker               # Docker 部署用环境变量（已忽略，不入库）
└── README.md                 # 本文件
```

## 数据库表概览

| 表名 | 说明 |
|---|---|
| `users` | 用户表 |
| `knowledge_bases` | 知识库表 |
| `kb_permissions` | 知识库权限表 |
| `documents` | 文档表 |
| `chunks` | 文档切片表 |
| `conversations` | 对话会话表 |
| `messages` | 对话消息表 |
| `token_usage` | Token 用量明细表 |
| `daily_token_summary` | 每日 Token / 费用 / 请求数汇总表（raw SQL 建表，手动触发写入） |
| `daily_qa_summary` | 每日问答统计数据表 |
| `daily_hot_questions` | 每日热门问题表 |
| `audit_logs` | 审计日志表 |
| `login_logs` | 登录日志表 |

## 快速开始

### 方式 A：Docker Compose（推荐）

```bash
# 1. 复制环境变量模板并填写真实值
cp .env.example .env
# 编辑 .env：填入 TONGYI_API_KEY、DEEPSEEK_API_KEY、MYSQL_PASSWORD、JWT_SECRET_KEY 等

# 2. 启动全部服务
docker compose up -d

# 3. 访问
# 前端 http://localhost:5173
# 后端 API 文档 http://localhost:8000/docs
# 后端 Redoc http://localhost:8000/redoc
```

### 方式 B：本地开发

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env   # 填写配置
# 注意：UPLOAD_DIR 默认值为 /app/data/uploads（容器路径）。本地开发若不覆盖，
# 上传文件会写到该绝对路径；如需落地到项目内，请在 .env 设置 UPLOAD_DIR=./data/uploads
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev
```

## 配置说明

所有配置通过环境变量注入，完整模板见 `.env.example` / `.env.template`。

**严禁提交真实 `.env`、`.env.local`、`.env.docker` 到仓库**，已通过 `.gitignore` 屏蔽。

关键配置项：

| 变量 | 说明 |
|---|---|
| `TONGYI_API_KEY` | 阿里通义嵌入模型 API Key |
| `DEEPSEEK_API_KEY` | DeepSeek 对话模型 API Key |
| `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | MySQL 连接 |
| `MILVUS_HOST` / `MILVUS_PORT` | Milvus 连接 |
| `REDIS_URL` | Redis 连接串（`CACHE_BACKEND=redis` 时作为共享缓存后端） |
| `CACHE_BACKEND` | 缓存后端：`memory`（默认，进程内）或 `redis`（共享，多副本一致） |
| `DAILY_SUMMARY_ENABLED` | 日报内置调度器开关（默认 `true`）；置 `false` 时改用外部 cron 调 `POST /api/reports/trigger-summary` |
| `DAILY_SUMMARY_HOUR` | 日报每日触发小时（本地时间 0-23，默认 `2`，汇总前一天） |
| `JWT_SECRET_KEY` | JWT 签名密钥（生产必须修改） |
| `INIT_ADMIN_USERNAME` / `INIT_ADMIN_PASSWORD` | 初始超管账号（生产必须修改；密码为空时不创建） |

## 测试

```bash
cd backend
pytest
```

## 部署

生产环境部署请参考 `docs/` 目录下文档，并务必：

1. 修改默认 `JWT_SECRET_KEY`。
2. 修改默认超管密码。
3. 使用 HTTPS 对外暴露服务。
4. 数据库启用独立用户并限制权限。

## 开发规范

- **分支模型**：
  - `main`：生产分支
  - `dev`：集成分支
  - `feature/*`：功能分支
  - `fix/*`：修复分支
- **提交规范**：遵循 [Angular Commit Message](https://github.com/angular/angular/blob/main/CONTRIBUTING.md)
  - `feat:` 新功能
  - `fix:` 修复
  - `docs:` 文档
  - `refactor:` 重构
  - `test:` 测试
  - `chore:` 构建/工具
- **合并要求**：通过 Pull Request + Code Review，禁止直接 push 到 `main`

## 大文件与模型管理

- 模型、压缩包、视频等大文件请使用 **Git LFS**，或托管至 OSS / HuggingFace / ModelScope。
- 本项目 `data/`、`logs/`、`backend/venv/`、`node_modules/` 已默认忽略。

## 贡献指南

1. Fork 本仓库
2. 从 `dev` 切出功能分支：`git checkout -b feature/your-feature`
3. 提交符合 Angular 规范的 commit
4. 向 `dev` 分支发起 Pull Request

## License

MIT
