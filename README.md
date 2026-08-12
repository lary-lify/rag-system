# 企业级 RAG 知识库系统 (rag-system)

> 面向企业的检索增强生成（RAG）知识库平台：多租户权限、多策略切片、向量检索、流式对话。

## 功能特性
- 🔐 三级权限模型（超管 / 部门管理员 / 普通用户）+ 知识库私有/共享
- 📚 四种切片策略：固定 Token / 语义 / 段落 / 标题层级
- 🔍 Milvus 向量检索 + 关键词混合召回
- 💬 SSE 流式对话，支持停止生成
- 📊 Token 用量计费与审计日志导出

## 技术栈
| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + Ant Design Vue + ECharts |
| 后端 | Python 3 + FastAPI |
| 向量库 | Milvus Standalone |
| 关系库 | MySQL 8.0 |
| 嵌入模型 | 阿里通义 text-embedding-v3 |
| 对话 LLM | DeepSeek (deepseek-chat) |

## 目录结构
```
rag-kb-system/
├── backend/        # FastAPI 服务
├── frontend/       # Vue3 前端
├── data/           # 运行时数据（上传/爬取，已忽略，保留 .gitkeep）
├── sql/            # 数据库初始化脚本
├── docs/           # 设计文档
└── scripts/        # 运维脚本
```

## 环境要求
- Python 3.10+
- Node.js 18+
- Docker & Docker Compose（推荐，含 MySQL/Milvus）
- Git LFS（若拉取模型/大文件）

## 快速开始

### 方式 A：Docker Compose（推荐）
```bash
cp .env.example .env      # 填入你的 API Key 与密码
docker compose up -d
# 前端 http://localhost:5173  后端 http://localhost:8000/docs
```

### 方式 B：本地开发
```bash
# 后端
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # 填值
uvicorn app.main:app --reload

# 前端
cd frontend && pnpm install && pnpm dev
```

## 配置说明
所有配置通过环境变量注入，见 `.env.example`。请勿将真实 `.env` / `.env.local` / `.env.docker` 提交到仓库。

## 测试
```bash
cd backend && pytest
```

## 部署
见 `docs/` 下部署文档。生产环境务必修改默认密钥与超管密码。

## 贡献指南
- 分支模型：`main`（生产）/ `dev`（集成）/ `feature/*`（开发）
- 提交遵循 [Angular 约定式提交](https://github.com/angular/angular/blob/main/CONTRIBUTING.md)
- 合并需通过 PR + Code Review

## License
MIT
