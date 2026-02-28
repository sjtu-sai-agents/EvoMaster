#!/usr/bin/env bash
set -euo pipefail

# 启动 FastAPI 服务
echo "deploy FastAPI service"
python api_server.py &
API_PID=$!

# 等待 API 服务启动
sleep 4

# 启动 MCP 适配器

python mcp_search_adapter.py &
MCP_PID=$!

# 等待终止信号
trap "kill $API_PID $MCP_PID; exit" INT TERM
wait