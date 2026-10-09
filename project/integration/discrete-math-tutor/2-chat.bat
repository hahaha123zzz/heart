@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo 离散数学助教：进入交互测试；输入 exit 退出
"%~dp0.venv\Scripts\python.exe" chat_cli.py
pause
