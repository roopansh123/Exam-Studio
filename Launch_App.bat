@echo off
title LKCS Exam Studio
cd /d "%~dp0"

echo Starting LKCS Exam Studio...

REM Check if the Windows venv exists
if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" run_desktop.py
    exit
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" run_desktop.py
    exit
) else (
    REM Fallback to system Python if venv is absent
    python run_desktop.py
)
