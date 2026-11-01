@echo off
title Video Downloader - Desktop GUI
cd /d "%~dp0"

echo ====================================================
echo Starting Video Downloader Desktop GUI...
echo ====================================================

:: Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Creating venv...
    python -m venv venv
    echo [INFO] Installing requirements...
    .\venv\Scripts\pip.exe install -r backend\requirements.txt pillow
)

:: Launch the Tkinter Desktop GUI
echo [INFO] Opening Desktop Application window...
start "" ".\venv\Scripts\pythonw.exe" "desktop_app\app.py"

exit