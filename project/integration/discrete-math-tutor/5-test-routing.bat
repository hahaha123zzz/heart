@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo 离散数学助教：运行离线回归检查
"%~dp0.venv\Scripts\python.exe" test_discrete_math.py
pause
