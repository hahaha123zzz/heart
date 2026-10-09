@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
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
echo.
"%PYTHON_EXE%" --version
start "" powershell -NoProfile -Command "Start-Sleep 3; Start-Process 'http://127.0.0.1:8000/'"
"%PYTHON_EXE%" -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
