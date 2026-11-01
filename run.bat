@echo off
title Video Downloader
echo ====================================================
echo Starting Video Downloader Application...
echo ====================================================

:: Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Creating venv...
    python -m venv venv
    echo [INFO] Installing requirements...
    .\venv\Scripts\pip.exe install -r backend\requirements.txt
)

:: Open the web browser after a brief 2-second delay in background
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"

:: Start the FastAPI server using the virtual environment python
echo [INFO] Server running at http://127.0.0.1:8000
echo [INFO] Press CTRL+C to stop the server anytime.
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
