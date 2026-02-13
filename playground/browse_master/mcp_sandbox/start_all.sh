#!/usr/bin/env bash
set -euo pipefail

# ============================================
# Browse-Master MCP Services - 一键启动脚本
# ============================================
#
# 用法:
#   ./start_all.sh              # 启动所有服务（默认端口）
#   ./start_all.sh stop         # 停止所有服务
#   ./start_all.sh status       # 查看服务状态
#   ./start_all.sh restart      # 重启所有服务
#
# 自定义端口:
#   SANDBOX_PORT=8001 SEARCH_PORT=8002 ./start_all.sh
#
# 默认端口:
#   - mcp-sandbox:   8001 (代码执行沙箱)
#   - search-tools:  8002 (搜索工具)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="${SCRIPT_DIR}/.pids"

# 默认端口
SANDBOX_PORT="${SANDBOX_PORT:-8001}"
SEARCH_PORT="${SEARCH_PORT:-8002}"
API_PORT="${API_PORT:-1234}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 确保 PID 目录存在
mkdir -p "${PID_DIR}"

start_sandbox() {
    log_info "启动 mcp-sandbox (端口: ${SANDBOX_PORT})..."
    cd "${SCRIPT_DIR}/MCP"
    PORT="${SANDBOX_PORT}" nohup python evomaster_mcp_server.py > "${PID_DIR}/sandbox.log" 2>&1 &
    echo $! > "${PID_DIR}/sandbox.pid"
    log_info "mcp-sandbox 已启动 (PID: $(cat ${PID_DIR}/sandbox.pid))"
}

start_search() {
    log_info "启动 search-tools (API端口: ${API_PORT}, MCP端口: ${SEARCH_PORT})..."
    cd "${SCRIPT_DIR}/api_proxy"

    # 启动 API 服务
    PORT="${API_PORT}" nohup python api_server.py > "${PID_DIR}/api.log" 2>&1 &
    echo $! > "${PID_DIR}/api.pid"

    # 等待 API 服务启动
    sleep 2

    # 启动 MCP 适配器
    MCP_PORT="${SEARCH_PORT}" nohup python browse_master_mcp_adapter.py > "${PID_DIR}/search.log" 2>&1 &
    echo $! > "${PID_DIR}/search.pid"

    log_info "search-tools 已启动 (API PID: $(cat ${PID_DIR}/api.pid), MCP PID: $(cat ${PID_DIR}/search.pid))"
}

stop_service() {
    local name=$1
    local pid_file="${PID_DIR}/${name}.pid"

    if [[ -f "${pid_file}" ]]; then
        local pid=$(cat "${pid_file}")
        if kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
            log_info "已停止 ${name} (PID: ${pid})"
        else
            log_warn "${name} 进程不存在"
        fi
        rm -f "${pid_file}"
    else
        log_warn "${name} PID 文件不存在"
    fi
}

stop_all() {
    log_info "停止所有服务..."
    stop_service "sandbox"
    stop_service "api"
    stop_service "search"
    log_info "所有服务已停止"
}

check_service() {
    local name=$1
    local port=$2
    local pid_file="${PID_DIR}/${name}.pid"

    if [[ -f "${pid_file}" ]]; then
        local pid=$(cat "${pid_file}")
        if kill -0 "${pid}" 2>/dev/null; then
            echo -e "  ${GREEN}●${NC} ${name}: 运行中 (PID: ${pid}, 端口: ${port})"
            return 0
        fi
    fi
    echo -e "  ${RED}○${NC} ${name}: 未运行"
    return 1
}

status() {
    echo "============================================"
    echo "Browse-Master MCP Services 状态"
    echo "============================================"
    check_service "sandbox" "${SANDBOX_PORT}" || true
    check_service "api" "${API_PORT}" || true
    check_service "search" "${SEARCH_PORT}" || true
    echo "============================================"
    echo ""
    echo "MCP 端点:"
    echo "  - mcp-sandbox:  http://127.0.0.1:${SANDBOX_PORT}/mcp"
    echo "  - search-tools: http://127.0.0.1:${SEARCH_PORT}/mcp"
    echo ""
    echo "日志文件: ${PID_DIR}/*.log"
}

start_all() {
    log_info "启动所有 Browse-Master MCP 服务..."
    echo ""
    start_sandbox
    start_search
    echo ""
    log_info "所有服务已启动！"
    echo ""
    status
}

# 主逻辑
case "${1:-start}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 2
        start_all
        ;;
    status)
        status
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac