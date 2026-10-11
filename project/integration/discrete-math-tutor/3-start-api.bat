@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set RAG_RERANK_DEVICE=cpu
set RAG_EMBED_DEVICE=cpu
if exist "%~dp0.venv-gpu\gpu-verified.json" if exist "%~dp0.venv-gpu\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv-gpu\Scripts\python.exe"
    set RAG_RERANK_DEVICE=cuda
    echo GPU reranker enabled.
)
if not exist "%PYTHON_EXE%" (
    echo Demo virtual environment was not found at:
    echo %PYTHON_EXE%
    echo Create .venv and install requirements.txt, then retry.
    pause
    exit /b 1
)
echo ==========================================================
echo  Start the Discrete Math Learning Platform
echo  The platform will open in your browser automatically:
echo  http://127.0.0.1:8000/
echo  API docs: http://127.0.0.1:8000/docs
echo  Keep this window open. Press Ctrl+C to stop.
echo ==========================================================
echo GPU 模型预热可能需要数分钟，请等待启动阶段日志。
echo.
"%PYTHON_EXE%" --version
start "" powershell -WindowStyle Hidden -NoProfile -Command "for ($taskAttempt=0; $taskAttempt -lt 300; $taskAttempt++) { try { $taskResponse=Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2; if ($taskResponse.StatusCode -eq 200) { Start-Process 'http://127.0.0.1:8000/'; break } } catch {}; Start-Sleep -Seconds 2 }"
"%PYTHON_EXE%" -u -m scripts.start_server
pause
