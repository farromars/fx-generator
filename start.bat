@echo off
REM ============================================================
REM fx-generator Windows 启动脚本（双击运行）
REM ============================================================

REM 切到 UTF-8 代码页，避免中文乱码
chcp 65001 >nul

setlocal ENABLEDELAYEDEXPANSION

REM 切到脚本所在目录
cd /d "%~dp0"

echo.
echo ============================================================
echo  fx-generator  Windows launcher
echo ============================================================

REM 1. 检查 Python
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 没有找到 python，请先装 Python 3.11+ 并加入 PATH
    echo         参考 INSTALL-WINDOWS.md
    pause
    exit /b 1
)

REM 2. 设 HuggingFace 国内镜像（如果当前会话没有设过）
if "%HF_ENDPOINT%"=="" (
    set HF_ENDPOINT=https://hf-mirror.com
    echo [info]  本次会话设置 HF_ENDPOINT=%HF_ENDPOINT%
) else (
    echo [info]  HF_ENDPOINT=%HF_ENDPOINT%
)

REM 3. Agnes API key 提示（不强制）
if "%AGNES_API_KEY%"=="" (
    echo [warn]  AGNES_API_KEY 未设置，云端 Agnes Provider 不可用
    echo         如要用，先在 PowerShell 跑：
    echo           [System.Environment]::SetEnvironmentVariable("AGNES_API_KEY", "你的key", "User")
    echo         或本次会话临时：
    echo           set AGNES_API_KEY=你的key
) else (
    echo [info]  AGNES_API_KEY 已设置
)

echo.
echo [info]  启动 fx-generator UI...
echo [info]  浏览器会自动打开 http://127.0.0.1:7860
echo [info]  关闭此窗口或按 Ctrl+C 停止服务
echo ------------------------------------------------------------
echo.

python app.py

REM 服务退出后停留，便于看错误
echo.
echo ------------------------------------------------------------
echo  fx-generator 已退出
echo ------------------------------------------------------------
pause
