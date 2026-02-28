# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for QLayout macOS app bundle.

Build with:
  pyinstaller build/QLayout.spec

This creates a single-file .app bundle optimized for macOS.
"""

# Read version from package
import sys
import os
spec_dir = os.path.dirname(os.path.abspath(SPECPATH))
sys.path.insert(0, spec_dir)
from cewe_layout import __version__

block_cipher = None

a = Analysis(
    ['../run_qlayout.py'],
    pathex=[],
    binaries=[],
    datas=[('../README.md', '.')],
    hiddenimports=[
        'cewe_layout',
        'cewe_layout.mcf_io',
        'cewe_layout.pdf_import',
        'cewe_layout.algorithms',
        'cewe_layout.utils',
        'cewe_layout.book',
        'cewe_layout.photoimprover',
        'cewe_layout.mimeo_import',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[
        'tkinterdnd2',  # Optional drag-drop, causes Tcl version conflicts when bundled
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='qlayout',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='macos/qlayout.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QLayout',
)

app = BUNDLE(
    coll,
    name='QLayout.app',
    icon='macos/qlayout.icns',
    bundle_identifier='com.vince.qlayout',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleDisplayName': 'QLayout',
        'CFBundleName': 'QLayout',
        'CFBundleIdentifier': 'com.vince.qlayout',
        'CFBundleVersion': __version__,
        'CFBundleShortVersionString': __version__,
    },
)
