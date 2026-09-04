# RAG 知识库系统 — 前端部署说明

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| 框架 | Vue 3 + Composition API | 3.5 |
| 构建 | Vite | 8.1 |
| UI | Ant Design Vue | ^4.2.6 |
| 路由 | Vue Router 4 | 4.x |
| 状态管理 | Pinia | 3.x |
| 图表 | ECharts | ^6.1.0 |
| 导出 | xlsx + file-saver | ^0.18.5 |
| 日期 | dayjs | 1.x |

## 快速启动

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 配置环境变量 (可选)

项目根目录创建 `.env.local`：

```bash
VITE_API_BASE_URL=/api   # 后端 API 基础路径
```

### 3. 启动开发服务器

```bash
npm run dev
```

开发服务器默认运行在 http://localhost:5173，已配置 `/api` 代理到 `http://localhost:8000`。

### 4. 生产构建

```bash
npm run build
```

构建产物输出到 `dist/` 目录。

## 目录结构

```
frontend/
├── src/
│   ├── api/              # 接口请求层 (axios 封装 + 各模块 API)
│   │   ├── index.ts      # axios 实例、拦截器
│   │   ├── auth.ts       # 登录/注册/改密
│   │   ├── users.ts      # 用户管理
│   │   ├── knowledgeBases.ts  # 知识库 CRUD + 权限
│   │   ├── documents.ts  # 文档上传/列表/删除
│   │   ├── conversations.ts   # 对话 + SSE 流式
│   │   ├── reports.ts    # 费用报表
│   │   ├── audit.ts      # 审计日志
│   │   └── config.ts     # 系统配置(只读)
│   ├── assets/           # 静态资源
│   ├── components/       # 公共组件
│   │   ├── common/       # 通用弹窗组件
│   │   ├── layout/       # 布局组件 (侧边栏/顶部栏)
│   │   └── charts/       # ECharts 图表组件
│   ├── composables/      # 组合式函数 (hooks)
│   │   ├── usePermission.ts  # 角色权限检查
│   │   ├── useExport.ts      # Excel/CSV 导出
│   │   └── useCost.ts        # 费用计算
│   ├── router/           # Vue Router 路由 + 守卫
│   ├── stores/           # Pinia 全局状态
│   │   ├── auth.ts       # 认证状态
│   │   ├── app.ts        # 主题/侧边栏
│   │   └── chat.ts       # SSE 流式对话状态
│   ├── styles/           # 全局样式
│   │   ├── variables.css # 设计 Token (浅色/深色)
│   │   └── global.css    # 全局基础样式
│   ├── types/            # TypeScript 类型定义
│   └── views/            # 页面组件 (9 个页面)
│       ├── login/        # 登录页
│       ├── dashboard/    # 首页仪表盘
│       ├── knowledgeBases/ # 知识库管理
│       ├── documents/    # 文件管理
│       ├── chat/         # 智能问答 (SSE 流式)
│       ├── reports/      # 统计报表
│       ├── users/        # 用户管理
│       ├── audit/        # 审计日志
│       └── config/       # 系统配置
├── vite.config.ts
└── package.json
```

## 功能验收清单

| # | 页面/功能 | 说明 | 状态 |
|---|----------|------|------|
| 1 | 登录页 | 用户名+密码登录，JWT Token | ✅ |
| 2 | 首页仪表盘 | 费用概览卡片 + ECharts趋势图 + 用户/KB排名 | ✅ |
| 3 | 知识库管理 | CRUD + 卡片网格 + 权限授权弹窗 | ✅ |
| 4 | 文件管理 | 拖拽上传 + 切分策略弹窗 + 进度条 + 切片预览 | ✅ |
| 5 | 智能问答 | SSE流式打字机 + 停止生成 + 来源溯源 + 多轮对话 | ✅ |
| 6 | 统计报表 | 全局/知识库/用户三维度报表 + ECharts + Excel导出 | ✅ |
| 7 | 用户管理 | 新建/编辑/禁用/删除用户 | ✅ |
| 8 | 审计日志 | 全链路日志查询 + CSV导出 | ✅ |
| 9 | 系统配置 | 只读分模块展示环境变量 | ✅ |
| 10 | 权限控制 | super_admin/dept_admin/user 三级路由+按钮鉴权 | ✅ |
| 11 | 深浅主题 | 一键切换深色/浅色主题，全页面适配 | ✅ |
| 12 | 费用计算 | 前端实时读取单价，本地计算预估费用 | ✅ |

## 与后端对接

### API 代理

开发环境下 `vite.config.ts` 已配置 `/api` 代理到 `http://localhost:8000`。

生产环境需要 Nginx 反向代理或直接使用后端服务的静态文件托管。

### 关键接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/auth/login` | POST | 登录 |
| `/api/auth/me` | GET | 当前用户信息 |
| `/api/knowledge-bases` | GET | 知识库列表 |
| `/api/documents/upload` | POST | 文件上传 (FormData) |
| `/api/conversations/chat` | POST | SSE 流式对话 |
| `/api/reports/cost-summary` | GET | 费用摘要 |
| `/api/config` | GET | 系统配置(只读) |
