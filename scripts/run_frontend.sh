#!/usr/bin/env bash
# ============================================
# RAG知识库系统 - Mac/Linux 前端启动脚本
# 功能：安装依赖，启动Vite开发服务器
# ============================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 获取脚本目录和项目根目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  RAG知识库系统 - 前端开发服务器${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

cd "$PROJECT_ROOT/frontend"

# ---- 检查 Node.js ----
echo -e "${BLUE}[检查]${NC} Node.js 环境..."
if ! command -v node &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} 未找到 Node.js！请安装 Node.js 18+"
    echo "       下载：https://nodejs.org/"
    echo "       或使用 nvm：https://github.com/nvm-sh/nvm"
    exit 1
fi
echo "Node.js $(node --version)"
echo -e "${GREEN}[OK]${NC}"

# ---- 检查 npm ----
echo ""
echo -e "${BLUE}[检查]${NC} npm..."
echo "npm $(npm --version)"
echo -e "${GREEN}[OK]${NC}"

# ---- 安装依赖 ----
echo ""
echo -e "${BLUE}[依赖]${NC} 检查并安装 npm 依赖..."
if [ ! -d "node_modules" ]; then
    echo "       首次运行，正在安装依赖（可能需要几分钟）..."
    npm install
else
    echo -e "${GREEN}[OK]${NC} node_modules 已存在"
    echo "       如需更新依赖，请手动运行：npm install"
fi

echo -e "${GREEN}[OK]${NC} 依赖就绪"

# ---- 启动 Vite ----
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  启动 Vite 开发服务器...${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "  前端页面:  http://localhost:5173"
echo "  后端代理:  /api -> http://localhost:8000"
echo "             （配置见 vite.config.ts）"
echo ""
echo "  按 Ctrl+C 停止服务"
echo -e "${BLUE}============================================${NC}"
echo ""

npm run dev

echo ""
echo "前端服务已停止"
