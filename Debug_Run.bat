@echo off
title LKCS Exam Studio - Debug Console
cd /d "%~dp0"

echo ========================================================
echo   LKCS Exam Studio - Live Debug Console
echo ========================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python run_desktop.py
    pause
    exit /b 0
)

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    py run_desktop.py
    pause
    exit /b 0
)

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" run_desktop.py
    pause
    exit /b 0
)

echo [ERROR] Python not found.
pause
