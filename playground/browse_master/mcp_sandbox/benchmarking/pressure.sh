#!/bin/bash

THREADS=$1   # threads
CONNECTIONS=$2   # connections
DURATION=$3   # duration
SCRIPT=$4   # lua script
URL=$5   # server url

# 检查是否提供了必需的参数
if [ -z "$THREADS" ] || [ -z "$CONNECTIONS" ] || [ -z "$DURATION" ] || [ -z "$SCRIPT" ] || [ -z "$URL" ]; then
  echo "Usage: $0 <threads> <connections> <duration> <script.lua> <url>"
  exit 1
fi

# 运行 wrk 命令
wrk -t$THREADS -c$CONNECTIONS -d$DURATION --timeout 30s -s $SCRIPT $URL/execute
