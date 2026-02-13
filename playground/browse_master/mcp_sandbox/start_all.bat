@echo off
setlocal enabledelayedexpansion

REM ============================================
REM Browse-Master MCP Services - Windows 启动脚本
REM ============================================

set SCRIPT_DIR=%~dp0
set PID_DIR=%SCRIPT_DIR%.pids\

REM 创建 PID 目录
if not exist "%PID_DIR%" mkdir "%PID_DIR%"

REM 设置默认端口
if "%SANDBOX_PORT%"=="" set SANDBOX_PORT=8001
if "%SEARCH_PORT%"=="" set SEARCH_PORT=8002
if "%API_PORT%"=="" set API_PORT=1234


REM 启动沙箱服务
:start_sandbox
call :log_info "启动 mcp-sandbox (端口: %SANDBOX_PORT%)..."
cd /d "%SCRIPT_DIR%MCP"
start /b cmd /c "set PORT=%SANDBOX_PORT% && python evomaster_mcp_server.py > "%PID_DIR%sandbox.log" 2>&1"
echo Started sandbox service
goto :eof

REM 启动搜索服务
:start_search
call :log_info "启动 search-tools (API端口: %API_PORT%, MCP端口: %SEARCH_PORT%)..."
cd /d "%SCRIPT_DIR%api_proxy"

REM 启动 API 服务
start /b cmd /c "set PORT=%API_PORT% && python api_server.py > "%PID_DIR%api.log" 2>&1"
echo Started API service

REM 等待 API 服务启动
timeout /t 2 /nobreak >nul

REM 启动 MCP 适配器
start /b cmd /c "set MCP_PORT=%SEARCH_PORT% && python browse_master_mcp_adapter.py > "%PID_DIR%search.log" 2>&1"
echo Started MCP adapter
call :log_info "search-tools 已启动"
goto :eof

REM 停止服务
:stop_service
set service_name=%1
if exist "%PID_DIR%%service_name%.pid" (
    REM 在Windows中，我们无法直接获取PID，所以这里只是删除日志文件
    del /q "%PID_DIR%%service_name%.log" 2>nul
    call :log_info "已停止 %service_name%"
) else (
    call :log_warn "%service_name% 服务似乎未运行"
)
goto :eof

:stop_all
call :log_info "停止所有服务..."
REM 在Windows中，我们需要手动关闭命令提示符窗口
call :log_info "请手动关闭所有打开的命令提示符窗口"
call :log_info "所有服务已停止"
goto :eof

REM 显示状态
:status
echo ============================================
echo Browse-Master MCP Services 状态
echo ============================================
echo.
echo MCP 端点:
echo   - mcp-sandbox:  http://127.0.0.1:%SANDBOX_PORT%/mcp
echo   - search-tools: http://127.0.0.1:%SEARCH_PORT%/mcp
echo.
echo 日志文件: %PID_DIR%*.log
echo.
echo 注意: Windows版本无法自动检测服务状态，请检查日志文件
goto :eof

REM 启动所有服务
:start_all
call :log_info "启动所有 Browse-Master MCP 服务..."
echo.
call :start_sandbox
call :start_search
echo.
call :log_info "所有服务已启动！"
echo.
call :status
goto :eof

REM 主逻辑
if "%1"=="stop" goto stop_all
if "%1"=="status" goto status
if "%1"=="restart" (
    call :stop_all
    timeout /t 2 /nobreak >nul
    call :start_all
    exit /b
)

REM 默认启动所有服务
call :start_all