#!/usr/bin/env bash
set -euo pipefail

# Start EvoMaster-compatible MCP server (Streamable HTTP)
#   Default http://127.0.0.1:8001/mcp (matches configs/x_master/mcp_config.json)
#
# MCP server provides: execute, reset_session, web_search, web_parse.
# web_search and web_parse need api_proxy (search, fetch_web, read_pdf), so we start it first.
#
# Optional: START_LEGACY_EXECUTE_SERVER=1 to also start legacy /execute server.
# Optional: SKIP_API_PROXY=1 to not start api_proxy (you must run it elsewhere).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
API_PORT="${API_PORT:-1234}"
PORT="${PORT:-8001}"
HOST="${HOST:-0.0.0.0}"

# Start api_proxy so web_search and web_parse can call /search, /fetch_web, /read_pdf
if [[ "${SKIP_API_PROXY:-0}" != "1" ]]; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 1 "http://127.0.0.1:${API_PORT}/search" 2>/dev/null || true)"
  if [[ "${CODE}" != "405" && "${CODE}" != "422" ]]; then
    echo "[deploy_server] starting api_proxy on :${API_PORT} ..."
    cd "${SANDBOX_ROOT}/api_proxy"
    PORT="${API_PORT}" python api_server.py &
    API_PID=$!
    echo "[deploy_server] api_proxy started (PID ${API_PID}), waiting 2s"
    sleep 2
  else
    echo "[deploy_server] api_proxy already responding on :${API_PORT}"
  fi
fi

if [[ "${START_LEGACY_EXECUTE_SERVER:-0}" == "1" ]]; then
  LEGACY_PORT="${LEGACY_PORT:-30008}"
  cd "${SCRIPT_DIR}"
  uvicorn tool_server:app --host "${HOST}" --port "${LEGACY_PORT}" --lifespan on --workers 1 &
  echo "[deploy_server] legacy /execute server started on :${LEGACY_PORT}"
fi

echo "[deploy_server] MCP server starting on ${HOST}:${PORT}/mcp"
cd "${SCRIPT_DIR}"
PORT="${PORT}" HOST="${HOST}" python evomaster_mcp_server.py

