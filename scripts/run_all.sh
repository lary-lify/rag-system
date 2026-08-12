#!/usr/bin/env bash
# ============================================
# RAG知识库系统 - Mac/Linux 一键启动脚本
# 启动顺序：MySQL → Milvus → 后端 → 前端
# 注意：MySQL和Milvus需预先安装并启动
# ============================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本目录和项目根目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  RAG知识库系统 - 本机环境一键启动${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

cd "$PROJECT_ROOT"

# ---- 步骤1：检查 .env 是否存在 ----
echo -e "${BLUE}[1/4]${NC} 检查环境变量配置..."
if [ ! -f ".env" ]; then
    echo -e "${RED}[ERROR]${NC} 未找到 .env 文件！"
    echo "       请先复制 .env.local 为 .env 并填写配置："
    echo -e "       ${YELLOW}cp .env.local .env${NC}"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} .env 配置文件已就绪"

# 加载 .env 环境变量
set -a
source .env
set +a

# ---- 步骤2：检查MySQL ----
echo ""
echo -e "${BLUE}[2/4]${NC} 检查 MySQL 连接..."
if command -v mysql &> /dev/null; then
    if mysql -h"${MYSQL_HOST:-localhost}" -P"${MYSQL_PORT:-3306}" -u"${MYSQL_USER:-root}" -p"${MYSQL_PASSWORD}" -e "SELECT 1" &>/dev/null 2>&1 || \
       mysql -h"${MYSQL_HOST:-localhost}" -P"${MYSQL_PORT:-3306}" -u"${MYSQL_USER:-root}" -e "SELECT 1" &>/dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC} MySQL 连接成功 (${MYSQL_HOST:-localhost}:${MYSQL_PORT:-3306})"
    else
        echo -e "${YELLOW}[WARN]${NC} MySQL 连接失败，请确认服务已启动"
    fi
else
    echo -e "${YELLOW}[WARN]${NC} 未检测到 mysql 命令，请确认 MySQL 已安装并运行"
fi

# ---- 步骤3：检查Milvus ----
echo ""
echo -e "${BLUE}[3/4]${NC} 检查 Milvus 连接..."
echo "       请确认 Milvus Standalone 已启动（端口19530），如未启动请运行："
echo "       - 下载：https://github.com/milvus-io/milvus/releases"
echo "       - 解压后运行：./milvus run standalone"
echo "       - 或使用脚本：bash scripts/start_milvus.sh"

# 检查 Milvus 端口
if command -v nc &> /dev/null || command -v netcat &> /dev/null; then
    NC_CMD=$(command -v nc || command -v netcat)
    if $NC_CMD -z "${MILVUS_HOST:-localhost}" "${MILVUS_PORT:-19530}" 2>/dev/null; then
        echo -e "${GREEN}[OK]${NC} Milvus 端口 ${MILVUS_PORT:-19530} 可达"
    else
        echo -e "${YELLOW}[WARN]${NC} Milvus 端口不可达，请先启动 Milvus Standalone"
    fi
fi

# ---- 步骤4：启动后端 ----
echo ""
echo -e "${BLUE}[4/4]${NC} 启动后端服务..."

# macOS 用 open，Linux 用 x-terminal-emulator 或 gnome-terminal
if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e "tell app \"Terminal\" to do script \"cd '$PROJECT_ROOT' && bash scripts/run_backend.sh\""
elif command -v gnome-terminal &> /dev/null; then
    gnome-terminal -- bash -c "cd '$PROJECT_ROOT' && bash scripts/run_backend.sh; exec bash"
elif command -v xterm &> /dev/null; then
    xterm -title "RAG-Backend" -e "cd '$PROJECT_ROOT' && bash scripts/run_backend.sh" &
else
    echo -e "${YELLOW}[NOTE]${NC} 无法打开新终端，请手动启动后端："
    echo "       bash scripts/run_backend.sh &"
fi

# 等待后端就绪
echo "       等待后端服务启动（约5秒）..."
sleep 5

# 健康检查
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} 后端服务已启动：http://localhost:8000"
else
    echo -e "${YELLOW}[WARN]${NC} 后端可能还在启动中，请稍候或检查 backend/logs/"
fi

# ---- 步骤5：启动前端 ----
echo ""
echo "启动前端开发服务器..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e "tell app \"Terminal\" to do script \"cd '$PROJECT_ROOT/frontend' && npm run dev\""
elif command -v gnome-terminal &> /dev/null; then
    gnome-terminal -- bash -c "cd '$PROJECT_ROOT/frontend' && npm run dev; exec bash"
elif command -v xterm &> /dev/null; then
    xterm -title "RAG-Frontend" -e "cd '$PROJECT_ROOT/frontend' && npm run dev" &
else
    echo -e "${YELLOW}[NOTE]${NC} 无法打开新终端，请手动启动前端："
    echo "       cd frontend && npm run dev &"
fi

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  全部服务启动中${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "  后端API:   http://localhost:8000"
echo "  API文档:   http://localhost:8000/docs"
echo "  前端页面:  http://localhost:5173"
echo "  超管登录:  ${INIT_ADMIN_USERNAME:-admin} / ${INIT_ADMIN_PASSWORD:-admin123}"
echo ""
echo "  后端日志:  ${PROJECT_ROOT}/backend/logs/"
echo "  上传文件:  ${PROJECT_ROOT}/backend/data/uploads/"
echo ""
