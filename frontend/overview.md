# RAG 知识库系统 — 前端完整交付概览

## 交付内容

**完整可运行的 Vue3 前端项目**，严格对齐需求文档、设计规范、后端接口。

## 项目结构 (42个源文件)

```
frontend/src/
├── api/          9 modules    (axios封装 + 全量接口)
├── stores/       3 stores     (auth/app/chat)
├── composables/  3 hooks      (permission/export/cost)
├── types/        7 files      (完整TS类型定义)
├── views/        9 pages      (全部页面)
├── components/   3 layout     (布局组件)
├── router/       1            (角色路由守卫)
├── styles/       2            (设计Token + 全局样式)
├── utils/        1            (格式化工具)
├── App.vue
└── main.ts
```

## 9个页面

| 页面 | 路由 | 权限 |
|------|------|------|
| 登录 | /login | 公开 |
| 首页仪表盘 | /dashboard | 超管/部门管理员 |
| 知识库管理 | /knowledge-bases | 超管/部门管理员 |
| 文件管理 | /documents | 超管/部门管理员 |
| 智能问答 | /chat | 全部角色 |
| 统计报表 | /reports | 超管/部门管理员 |
| 用户管理 | /users | 超管/部门管理员 |
| 审计日志 | /audit | 超管/部门管理员 |
| 系统配置 | /config | 超管/部门管理员 |

## 核心技术特点

- ✅ Vue3 + Vite + Composition API + TypeScript
- ✅ Ant Design Vue + 商务蓝设计Token + 深浅双主题
- ✅ Pinia 全局状态管理
- ✅ Vue Router 角色级动态路由守卫
- ✅ SSE 流式对话打字机渲染 + 停止生成
- ✅ fetch + ReadableStream POST SSE (突破 EventSource GET 限制)
- ✅ ECharts 费用趋势可视化
- ✅ 前端 Excel 导出 (xlsx库)
- ✅ 费用实时计算 (前端读取环境变量单价)
- ✅ 文件拖拽上传 + 切分策略弹窗 + 进度条
- ✅ 零编译错误，TypeScript 6.0.3 + Vite 8.1 构建通过

## 启动方式

```bash
cd frontend && npm install && npm run dev
```
