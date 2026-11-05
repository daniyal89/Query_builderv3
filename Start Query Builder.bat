@echo off
title Query Builder
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python virtual environment not found at .venv\Scripts\python.exe
    echo Create it first:  python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting Query Builder... the browser will open shortly.
echo Close this window to stop the app.
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
