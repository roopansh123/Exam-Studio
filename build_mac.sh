#!/usr/bin/env bash
set -e

echo "========================================================"
echo "  Building LKCS Exam Studio for macOS (.app & .dmg)"
echo "  Lord Krishna Convent School"
echo "========================================================"

# Determine Python / PyInstaller executable
if [ -f ".venv/bin/pyinstaller" ]; then
    PYINSTALLER=".venv/bin/pyinstaller"
    PYTHON=".venv/bin/python"
elif [ -f "venv/bin/pyinstaller" ]; then
    PYINSTALLER="venv/bin/pyinstaller"
    PYTHON="venv/bin/python"
else
    PYINSTALLER="pyinstaller"
    PYTHON="python3"
fi

echo "Using Python: $($PYTHON --version)"
echo "Using PyInstaller: $($PYINSTALLER --version)"

# Run PyInstaller
echo "Running PyInstaller on macOS..."
$PYINSTALLER --clean --noconfirm LKCSExamStudio.spec

# Check if .app exists in dist
if [ ! -d "dist/LKCSExamStudio.app" ]; then
    echo "[ERROR] dist/LKCSExamStudio.app was not created!"
    exit 1
fi

echo "Created dist/LKCSExamStudio.app successfully!"

# Create DMG disk image using create-dmg or native hdiutil
echo "Creating macOS DMG installer..."
DMG_PATH="dist/LKCSExamStudio.dmg"
rm -f "$DMG_PATH"

if command -v create-dmg &> /dev/null; then
    create-dmg \
      --volname "LKCS Exam Studio Installer" \
      --window-pos 200 120 \
      --window-size 600 400 \
      --icon-size 100 \
      --icon "LKCSExamStudio.app" 175 120 \
      --hide-extension "LKCSExamStudio.app" \
      --app-drop-link 425 120 \
      "$DMG_PATH" \
      "dist/LKCSExamStudio.app"
else
    echo "create-dmg not found, using native macOS hdiutil..."
    hdiutil create -volname "LKCSExamStudio" -srcfolder "dist/LKCSExamStudio.app" -ov -format UDZO "$DMG_PATH"
fi

echo "========================================================"
echo "  BUILD SUCCESSFUL!"
echo "  macOS App: dist/LKCSExamStudio.app"
echo "  macOS DMG: $DMG_PATH"
echo "========================================================"
