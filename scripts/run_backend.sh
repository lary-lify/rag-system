#!/usr/bin/env bash
# ============================================
# RAG知识库系统 - Mac/Linux 后端启动脚本
# 功能：加载 .env 环境变量，创建必要目录，启动 uvicorn
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
echo -e "${BLUE}  RAG知识库系统 - 后端服务${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

cd "$PROJECT_ROOT/backend"

# ---- 检查 Python ----
echo -e "${BLUE}[检查]${NC} Python 环境..."
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} 未找到 Python！请安装 Python 3.11+"
    echo "       下载：https://www.python.org/downloads/"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)
echo "$($PYTHON --version)"
echo -e "${GREEN}[OK]${NC}"

# ---- 检查 .env 文件 ----
echo ""
echo -e "${BLUE}[检查]${NC} 环境变量文件..."
if [ ! -f "../.env" ]; then
    echo -e "${RED}[ERROR]${NC} 未找到 ../.env 文件！"
    echo "       请从 .env.local 复制并填写配置："
    echo -e "       ${YELLOW}cp .env.local .env${NC}"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} .env 已就绪"

# 加载 .env 环境变量
set -a
source ../.env
set +a

# ---- 创建必要目录 ----
echo ""
echo -e "${BLUE}[目录]${NC} 创建存储目录..."
mkdir -p data/uploads
mkdir -p data/crawls
mkdir -p logs
echo -e "${GREEN}[OK]${NC} 目录就绪"

# ---- 检查/创建虚拟环境 ----
echo ""
echo -e "${BLUE}[依赖]${NC} 检查 Python 依赖..."
if [ ! -d "venv" ]; then
    echo "       正在创建虚拟环境..."
    $PYTHON -m venv venv
    echo -e "${GREEN}[OK]${NC} 虚拟环境已创建"
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "       安装/更新依赖..."
pip install -r requirements.txt -q --disable-pip-version-check
echo -e "${GREEN}[OK]${NC} 依赖就绪"

# ---- 启动服务 ----
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  启动 FastAPI 服务...${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "  后端API:   http://localhost:8000"
echo "  API文档:   http://localhost:8000/docs"
echo "  健康检查:  http://localhost:8000/api/health"
echo "  日志输出:  ${PROJECT_ROOT}/backend/logs/"
echo ""
echo "  按 Ctrl+C 停止服务"
echo -e "${BLUE}============================================${NC}"
echo ""

# 启动 uvicorn
python -m uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT:-8000}" --reload --log-level info

echo ""
echo "后端服务已停止"
