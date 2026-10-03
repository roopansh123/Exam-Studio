# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

added_files = [
    ('app/templates', 'app/templates'),
    ('app/static', 'app/static'),
    ('uploads', 'uploads'),
    ('question_paper.db', '.'),
]

hidden_imports = [
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.wsproto_impl',
    'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'fastapi',
    'pydantic',
    'starlette',
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    'jinja2',
    'multipart',
    'multipart.multipart',
    'python_multipart',
    'docx',
    'docx.oxml',
    'docx.oxml.ns',
    'docx.oxml.text.paragraph',
    'docx.oxml.table',
    'docx.shared',
    'docx.enum.text',
    'docx.enum.table',
    'qrcode',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'sqlite3',
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'webview.platforms.cocoa',
]

a = Analysis(
    ['run_desktop.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LKCSExamStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # Windowed desktop application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.icns' if sys.platform == 'darwin' else 'app_icon.ico'
)

# For macOS .app bundle creation
app = BUNDLE(
    exe,
    name='LKCSExamStudio.app',
    icon='app_icon.icns',
    bundle_identifier='com.lkcs.examstudio',
)
