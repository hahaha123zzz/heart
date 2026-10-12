@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PYTHON_EXE%" (echo 请安装 Python 3.11 或 3.14，或建立 .venv & pause & exit /b 1)
echo 请先启动 3-start-api.bat；本工具使用正式账号登录。
"%PYTHON_EXE%" chat_cli.py
pause
