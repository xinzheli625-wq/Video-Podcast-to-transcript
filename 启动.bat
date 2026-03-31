@echo off
chcp 65001 >nul
title 小宇宙转文字 - 一键启动
cd /d "%~dp0"

echo.
echo ============================================
echo    小宇宙播客转文字 - 一键启动
echo ============================================
echo.

:: 激活虚拟环境
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [OK] 虚拟环境已激活
) else (
    echo [WARN] 未找到虚拟环境，使用系统 Python
)

:: 启动 API
echo.
echo [1/2] 启动 API 服务...
start "API Service - 不要关闭此窗口" cmd /k "cd /d "%~dp0" && echo. && echo =================================== && echo API 服务启动中... && echo 请保持此窗口打开 && echo =================================== && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

:: 等待 API 启动
echo.
echo [2/2] 等待服务就绪...
:wait_loop
timeout /t 1 >nul
python -c "import socket; socket.create_connection(('localhost', 8000), timeout=1)" 2>nul
if errorlevel 1 (
    echo      等待 API 就绪...
    goto wait_loop
)
echo [OK] API 已就绪

:: 打开浏览器
echo.
echo ============================================
echo    服务已启动！
echo ============================================
echo.
echo 正在打开浏览器...
timeout /t 2 >nul
start http://localhost:8000/frontend/index.html

echo.
echo 提示：
echo   - 保持 API 服务窗口打开
echo   - 转录任务会在后台自动执行
echo   - 关闭 API 窗口会停止服务
echo.
echo 按任意键关闭此启动器
echo.
pause >nul
