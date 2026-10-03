@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ========================================================
echo   Building LKCS Exam Studio for Windows (.exe)
echo   Lord Krishna Convent School
echo ========================================================
echo.

REM 1. Clean previous build caches
if exist "build\LKCSExamStudio" (
    echo Cleaning previous build directory...
    rmdir /s /q "build\LKCSExamStudio" >nul 2>&1
)
if exist "dist\EduPaperPro.exe" (
    del /f /q "dist\EduPaperPro.exe" >nul 2>&1
)

REM 2. Check for pre-installed venv
if exist "venv\Scripts\pyinstaller.exe" (
    echo Using pre-installed environment from venv...
    echo Compiling LKCSExamStudio.exe with PyInstaller...
    "venv\Scripts\pyinstaller.exe" --clean --noconfirm LKCSExamStudio.spec
    goto :check_result
)

if exist ".venv\Scripts\pyinstaller.exe" (
    echo Using pre-installed environment from .venv...
    echo Compiling LKCSExamStudio.exe with PyInstaller...
    ".venv\Scripts\pyinstaller.exe" --clean --noconfirm LKCSExamStudio.spec
    goto :check_result
)

REM 3. Fallback to system Python if venv is missing
echo Virtual environment not found, looking for system Python...
set PY_CMD=python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    py --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PY_CMD=py
    ) else (
        echo [ERROR] Python was not found on this system.
        pause
        exit /b 1
    )
)

echo Installing dependencies...
!PY_CMD! -m pip install -r requirements.txt
!PY_CMD! -m pip install pyinstaller

echo Compiling LKCSExamStudio.exe...
!PY_CMD! -m PyInstaller --clean --noconfirm LKCSExamStudio.spec

:check_result

echo.
echo [Step 3/3] Verifying output...
if exist "dist\LKCSExamStudio.exe" (
    echo.
    echo ========================================================
    echo   BUILD SUCCESSFUL!
    echo   Your new app is located at:
    echo   dist\LKCSExamStudio.exe
    echo.
    echo   Features included:
    echo   * Lord Krishna Convent School branding & Blue LK Icon
    echo   * Fixed Windows startup sync (no more ERR_CONNECTION_REFUSED)
    echo   * MCQ base font size auto-scaling
    echo   * Admin Blueprint optional section column
    echo ========================================================
) else (
    echo.
    echo [ERROR] Build failed. Please review the PyInstaller messages above.
)

echo.
pause

