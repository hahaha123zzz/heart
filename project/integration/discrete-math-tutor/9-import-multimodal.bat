@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Demo virtual environment was not found. Create .venv and install requirements.txt first.
    pause
    exit /b 1
)
echo Converting legacy Word textbooks. This can take several minutes.
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts\convert_legacy_docs.ps1
if errorlevel 1 (
    echo Word conversion reported errors. Check knowledge\imported_wordopenxml\conversion.log
    pause
    exit /b 1
)
"%PYTHON_EXE%" -X utf8 scripts\parse_converted_textbook.py
if errorlevel 1 (
    echo Structured extraction failed.
    pause
    exit /b 1
)
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts\convert_multimodal_previews.ps1
if errorlevel 1 (
    echo Image preview conversion failed.
    pause
    exit /b 1
)
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts\extract_word_vectors.ps1
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts\convert_multimodal_previews.ps1 -CatalogName vector_catalog.json
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" -X utf8 scripts\finalize_multimodal_import.py
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts\map_vector_positions.ps1
if errorlevel 1 exit /b 1
echo Extraction finished. See knowledge\extracted_multimodal\summary.json and asset_catalog.json.
pause
