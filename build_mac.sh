#!/usr/bin/env bash
set -e

echo "========================================================"
echo "  Building LKCS Exam Studio for macOS (.app & .dmg)"
echo "  Lord Krishna Convent School"
echo "========================================================"

# Configure target architecture if specified
DMG_NAME="${1:-LKCSExamStudio}"
if [[ "$DMG_NAME" == *"Intel"* ]] || [[ "$DMG_NAME" == *"x86_64"* ]]; then
    export TARGET_ARCH="x86_64"
    ARCH_CMD="arch -x86_64"
    echo "Target architecture set to: Intel (x86_64)"
elif [[ "$DMG_NAME" == *"AppleSilicon"* ]] || [[ "$DMG_NAME" == *"arm64"* ]]; then
    export TARGET_ARCH="arm64"
    ARCH_CMD=""
    echo "Target architecture set to: Apple Silicon (arm64)"
else
    ARCH_CMD=""
fi

# Determine Python / PyInstaller executable
if [ -n "$VIRTUAL_ENV" ] && [ -f "$VIRTUAL_ENV/bin/pyinstaller" ]; then
    PYINSTALLER="$VIRTUAL_ENV/bin/pyinstaller"
    PYTHON="$VIRTUAL_ENV/bin/python"
elif [ -f "venv_x86_64/bin/pyinstaller" ]; then
    PYINSTALLER="venv_x86_64/bin/pyinstaller"
    PYTHON="venv_x86_64/bin/python"
elif [ -f ".venv/bin/pyinstaller" ]; then
    PYINSTALLER=".venv/bin/pyinstaller"
    PYTHON=".venv/bin/python"
elif [ -f "venv/bin/pyinstaller" ]; then
    PYINSTALLER="venv/bin/pyinstaller"
    PYTHON="venv/bin/python"
else
    PYINSTALLER="pyinstaller"
    PYTHON="python3"
fi

echo "Using Python: $($ARCH_CMD $PYTHON --version)"
echo "Using PyInstaller: $($ARCH_CMD $PYINSTALLER --version)"

# Run PyInstaller
echo "Running PyInstaller on macOS (Target: ${TARGET_ARCH:-Native})..."
$ARCH_CMD $PYINSTALLER --clean --noconfirm LKCSExamStudio.spec

# Check if .app exists in dist
if [ ! -d "dist/LKCSExamStudio.app" ]; then
    echo "[ERROR] dist/LKCSExamStudio.app was not created!"
    exit 1
fi

echo "Created dist/LKCSExamStudio.app successfully!"

# Create DMG disk image using create-dmg or native hdiutil
DMG_PATH="dist/${DMG_NAME}.dmg"
echo "Creating macOS DMG installer at $DMG_PATH..."
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

if [ "$DMG_PATH" != "dist/LKCSExamStudio.dmg" ]; then
    cp "$DMG_PATH" "dist/LKCSExamStudio.dmg"
fi

echo "========================================================"
echo "  BUILD SUCCESSFUL!"
echo "  macOS App: dist/LKCSExamStudio.app"
echo "  macOS DMG: $DMG_PATH"
echo "========================================================"
