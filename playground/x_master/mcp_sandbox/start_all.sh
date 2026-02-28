#!/usr/bin/env bash
set -euo pipefail

# ============================================
# X-Master MCP Services（与 deploy_server.sh 一致）
# ============================================
#
# 只启动 api_proxy + mcp-sandbox（execute, reset_session, web_search, web_parse）。
# 不启动 search-tools；mcp-sandbox 已包含搜索与解析能力。
#
# 用法:
#   ./start_all.sh              # 启动服务（后台）
#   ./start_all.sh stop         # 停止所有服务
#   ./start_all.sh status       # 查看服务状态
#   ./start_all.sh restart      # 重启所有服务
#
# 可选环境变量:
#   SKIP_API_PROXY=1            不启动 api_proxy（需自行在别处启动）
#   START_LEGACY_EXECUTE_SERVER=1  同时启动 legacy /execute 服务 (默认 30008)
#
# 默认端口:
#   - api_proxy:  1234
#   - mcp-sandbox: 8001

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="${SCRIPT_DIR}/.pids"

SANDBOX_PORT="${SANDBOX_PORT:-8001}"
API_PORT="${API_PORT:-1234}"
LEGACY_PORT="${LEGACY_PORT:-30008}"
HOST="${HOST:-0.0.0.0}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

mkdir -p "${PID_DIR}"

start_api_proxy() {
    if [[ "${SKIP_API_PROXY:-0}" == "1" ]]; then
        log_info "跳过 api_proxy (SKIP_API_PROXY=1)"
        return 0
    fi
    CODE="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 1 "http://127.0.0.1:${API_PORT}/search" 2>/dev/null || true)"
    if [[ "${CODE}" == "405" || "${CODE}" == "422" ]]; then
        log_info "api_proxy 已在运行 (:${API_PORT})"
        return 0
    fi
    log_info "启动 api_proxy (端口: ${API_PORT})..."
    cd "${SCRIPT_DIR}/api_proxy"
    PORT="${API_PORT}" nohup python api_server.py > "${PID_DIR}/api.log" 2>&1 &
    echo $! > "${PID_DIR}/api.pid"
    log_info "api_proxy 已启动 (PID: $(cat ${PID_DIR}/api.pid))"
    sleep 2
}

start_sandbox() {
    log_info "启动 mcp-sandbox (端口: ${SANDBOX_PORT})..."
    cd "${SCRIPT_DIR}/MCP"
    PORT="${SANDBOX_PORT}" HOST="${HOST}" nohup python evomaster_mcp_server.py > "${PID_DIR}/sandbox.log" 2>&1 &
    echo $! > "${PID_DIR}/sandbox.pid"
    log_info "mcp-sandbox 已启动 (PID: $(cat ${PID_DIR}/sandbox.pid))"
}

start_legacy() {
    if [[ "${START_LEGACY_EXECUTE_SERVER:-0}" != "1" ]]; then
        return 0
    fi
    log_info "启动 legacy /execute 服务 (端口: ${LEGACY_PORT})..."
    cd "${SCRIPT_DIR}/MCP"
    nohup uvicorn tool_server:app --host "${HOST}" --port "${LEGACY_PORT}" --lifespan on --workers 1 > "${PID_DIR}/legacy.log" 2>&1 &
    echo $! > "${PID_DIR}/legacy.pid"
    log_info "legacy 已启动 (PID: $(cat ${PID_DIR}/legacy.pid))"
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
    stop_service "legacy"
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
    echo "X-Master MCP Services 状态"
    echo "============================================"
    check_service "api" "${API_PORT}" || true
    check_service "sandbox" "${SANDBOX_PORT}" || true
    if [[ "${START_LEGACY_EXECUTE_SERVER:-0}" == "1" ]]; then
        check_service "legacy" "${LEGACY_PORT}" || true
    fi
    echo "============================================"
    echo ""
    echo "MCP 端点:"
    echo "  - mcp-sandbox: http://127.0.0.1:${SANDBOX_PORT}/mcp"
    echo ""
    echo "日志文件: ${PID_DIR}/*.log"
}

start_all() {
    log_info "启动 X-Master MCP 服务 (api_proxy + mcp-sandbox)..."
    echo ""
    start_api_proxy
    start_sandbox
    start_legacy
    echo ""
    log_info "启动完成！"
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
