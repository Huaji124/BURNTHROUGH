@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo 安装依赖...
pip install -e . pyinstaller
echo 开始打包...
pyinstaller --noconfirm --windowed --name BURNTHROUGH --paths src --add-data "data;data" scripts\run_ui.py
echo.
echo 打包完成: dist\BURNTHROUGH\BURNTHROUGH.exe
pause
