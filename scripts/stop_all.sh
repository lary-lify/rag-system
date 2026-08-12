#!/usr/bin/env bash
# ============================================
# RAG知识库系统 - Mac/Linux 停止所有服务脚本
# ============================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  停止 RAG 知识库系统所有服务${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# ---- 停止后端 ----
echo -e "${BLUE}[1/2]${NC} 停止后端服务（端口8000）..."
BACKEND_PIDS=$(lsof -ti:8000 2>/dev/null || true)
if [ -n "$BACKEND_PIDS" ]; then
    kill $BACKEND_PIDS 2>/dev/null || true
    sleep 1
    # 强制杀死残留进程
    lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null || true
    echo -e "${GREEN}[OK]${NC} 后端服务已停止 (PID: $BACKEND_PIDS)"
else
    echo -e "${YELLOW}[NOTE]${NC} 未发现运行中的后端服务"
fi

# ---- 停止前端 ----
echo -e "${BLUE}[2/2]${NC} 停止前端服务（端口5173）..."
FRONTEND_PIDS=$(lsof -ti:5173 2>/dev/null || true)
if [ -n "$FRONTEND_PIDS" ]; then
    kill $FRONTEND_PIDS 2>/dev/null || true
    sleep 1
    lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null || true
    echo -e "${GREEN}[OK]${NC} 前端服务已停止 (PID: $FRONTEND_PIDS)"
else
    echo -e "${YELLOW}[NOTE]${NC} 未发现运行中的前端服务"
fi

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${GREEN}  所有服务已停止${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "  MySQL 和 Milvus 服务不会被此脚本停止，"
echo "  如需停止请手动操作："
echo "    MySQL (Mac):   brew services stop mysql"
echo "    MySQL (Linux): sudo systemctl stop mysql"
echo "    Milvus:        在Milvus窗口按 Ctrl+C"
echo ""
