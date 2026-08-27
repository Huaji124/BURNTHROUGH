@echo off
chcp 65001 >nul
cd /d %~dp0
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10 或更高版本。
    pause
    exit /b 1
)

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe scripts\run_ui.py
) else (
    echo 首次运行，正在创建虚拟环境并安装依赖...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -e . pyinstaller
    python scripts\run_ui.py
)
pause
