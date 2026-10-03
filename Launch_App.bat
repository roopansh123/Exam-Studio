@echo off
title LKCS Exam Studio
cd /d "%~dp0"

echo ========================================================
echo   Launching LKCS Exam Studio...
echo   Lord Krishna Convent School
echo ========================================================
echo.

REM 1. Try system Python first (recommended on Windows)
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Starting using Python...
    start "" python run_desktop.py
    exit /b 0
)

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Starting using Python Launcher...
    start "" py run_desktop.py
    exit /b 0
)

REM 2. Try bundled venv
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -c "exit(0)" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo Starting using bundled environment...
        start "" "venv\Scripts\python.exe" run_desktop.py
        exit /b 0
    )
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "exit(0)" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo Starting using bundled environment...
        start "" ".venv\Scripts\python.exe" run_desktop.py
        exit /b 0
    )
)

echo [ERROR] Python is not installed on this computer.
echo Please install Python 3.11 from https://www.python.org/downloads/
echo (Check "Add Python to PATH" during installation)
echo.
pause
