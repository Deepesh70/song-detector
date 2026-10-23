# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

datas = [
    ('assets/icon.png', 'assets'),
    ('assets/icon.ico', 'assets'),
]

# Collect certifi certificates
try:
    datas += collect_data_files('certifi')
except Exception:
    pass

hiddenimports = [
    'soundcard',
    'soundcard.mediafoundation',
    'cffi',
    'certifi',
    'httpx',
    'numpy',
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'client',
    'client.gui',
    'client.gui.styles',
    'client.gui.visualizer',
    'client.gui.worker',
    'client.gui.main_window',
    'client.gui.tabs',
    'client.gui.tabs.identify_tab',
    'client.gui.tabs.history_tab',
    'client.gui.tabs.settings_tab',
    'client.config',
    'client.history_store',
    'client.capture',
    'client.preprocessor',
    'client.direct_recognizer',
    'client.notifier',
]

excludes = [
    'backend',
    'worker',
    'psycopg',
    'psycopg2',
    'asyncpg',
    'fastapi',
    'uvicorn',
    'redis',
    'fakeredis',
    'soundfile',
    'matplotlib',
    'tkinter',
    'IPython',
    'PyQt6.QtQml',
    'PyQt6.QtQuick',
    'PyQt6.QtPdf',
    'PyQt6.QtNetwork',
    'PyQt6.QtOpenGL',
    'PyQt6.QtTest',
]

a = Analysis(
    ['client/gui_app.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name='HearThis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
