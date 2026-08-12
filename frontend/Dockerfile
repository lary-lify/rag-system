# ============================================
# 前端生产构建 + Nginx 镜像
# ============================================
# 第一阶段：Node 构建
FROM node:22-alpine AS build-stage

WORKDIR /app

# 安装依赖（利用 Docker 层缓存）
COPY package.json package-lock.json* ./
RUN npm ci --silent

# 复制源码并构建
COPY . .
RUN npm run build

# 第二阶段：Nginx 运行
FROM nginx:1.27-alpine

# 复制构建产物
COPY --from=build-stage /app/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
