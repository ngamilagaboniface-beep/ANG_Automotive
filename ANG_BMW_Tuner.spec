# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

a = Analysis(
    ['desktop_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('ang_telematics', 'ang_telematics'),
    ],
    hiddenimports=[
        'cryptography',
        'cryptography.hazmat.backends.default_backend',
        'cryptography.hazmat.primitives.asymmetric.rsa',
        'cryptography.hazmat.primitives.asymmetric.padding',
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.hashes',
        'cryptography.x509',
        'sqlite3',
        'numpy',
        'scipy',
        'pandas',
        'flask',
        'flask_sqlalchemy',
        'flask_login',
        'jinja2',
        'werkzeug',
        'webview',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'test'],
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
    name='ANG_BMW_Tuner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to True so diagnostic/flashing logs remain visible, or False for purely windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
