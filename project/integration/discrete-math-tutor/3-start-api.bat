@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PYTHON_EXE%" (
    echo 请安装 Python 3.11 或 3.14，或建立 .venv。
    pause
    exit /b 1
)
echo ==========================================================
echo  Start the Discrete Math Learning Platform
echo  The platform will open in your browser automatically:
echo  http://127.0.0.1:8000/
echo  API docs: http://127.0.0.1:8000/docs
echo  Keep this window open. Press Ctrl+C to stop.
echo  真实 AI 问答：复制 .env.example 为 .env，填入密钥，保持 LLM_MOCK=0。
echo  LLM_MOCK=1 仅测试流程，返回固定模拟模板。
echo ==========================================================
echo.
"%PYTHON_EXE%" --version
start "" powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 60;$i++){try{$r=Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2;if($r.StatusCode -eq 200){Start-Process 'http://127.0.0.1:8000/';break}}catch{};Start-Sleep -Seconds 1}"
"%PYTHON_EXE%" -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
