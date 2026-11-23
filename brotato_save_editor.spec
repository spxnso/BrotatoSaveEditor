# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for BrotatoSaveEditor.
# Build:  pip install -r requirements-build.txt && pyinstaller --clean --noconfirm brotato_save_editor.spec
# Output: dist/BrotatoSaveEditor[.exe]
import os
import sys

block_cipher = None

datas = [
    ("data", "data"),
    ("assets", "assets"),
]

a = Analysis(
    ["brotato_save_editor.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BrotatoSaveEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/app_icon.ico" if sys.platform == "win32" else None,
)
