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

REM 1.5 Ensure cloudflared.exe is downloaded for tunnel support
if not exist "app\bin\cloudflared.exe" (
    echo Downloading cloudflared.exe for permanent internet tunnel...
    if not exist "app\bin" mkdir "app\bin"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe', 'app\bin\cloudflared.exe')" >nul 2>&1
)

REM 2. Check for working pre-installed venv
if exist "venv\Scripts\pyinstaller.exe" (
    "venv\Scripts\python.exe" -c "exit(0)" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo Using pre-installed environment from venv...
        echo Compiling LKCSExamStudio.exe with PyInstaller...
        "venv\Scripts\pyinstaller.exe" --clean --noconfirm LKCSExamStudio.spec
        goto :check_result
    )
)

if exist ".venv\Scripts\pyinstaller.exe" (
    ".venv\Scripts\python.exe" -c "exit(0)" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo Using pre-installed environment from .venv...
        echo Compiling LKCSExamStudio.exe with PyInstaller...
        ".venv\Scripts\pyinstaller.exe" --clean --noconfirm LKCSExamStudio.spec
        goto :check_result
    )
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
echo [Step 3/4] Verifying standalone executable...
if not exist "dist\LKCSExamStudio.exe" (
    echo.
    echo [ERROR] Build failed. dist\LKCSExamStudio.exe was not created.
    pause
    exit /b 1
)

echo [Step 4/4] Building Windows Setup Installer (Inno Setup)...
set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "!ISCC_PATH!" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)
where iscc >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    iscc installer.iss
) else if exist "!ISCC_PATH!" (
    "!ISCC_PATH!" installer.iss
) else (
    echo [NOTE] Inno Setup compiler (iscc.exe) not found on this PC.
    echo Standalone executable is ready at dist\LKCSExamStudio.exe!
    echo To build the Setup wizard, install Inno Setup from https://jrsoftware.org/isdl.php
)

echo.
echo ========================================================
echo   BUILD COMPLETE!
echo.
if exist "dist\installer\LKCSExamStudio_Setup.exe" (
    echo   Setup Installer:  dist\installer\LKCSExamStudio_Setup.exe
)
echo   Standalone .EXE:  dist\LKCSExamStudio.exe
echo.
echo   Features included:
echo   * Lord Krishna Convent School branding & Blue LK Icon
echo   * Desktop shortcut & Start Menu integration
echo   * Fixed Windows startup sync (no more ERR_CONNECTION_REFUSED)
echo   * MCQ base font size auto-scaling
echo   * Admin Blueprint optional section column
echo ========================================================

echo.
pause

