# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH)
a = Analysis(
    [str(ROOT / 'src' / 'desktop.py')],
    pathex=[str(ROOT / 'src')],
    binaries=[],
    datas=[
        (str(ROOT / 'output/pdf/C130J_CDU_Helper_User_Guide.pdf'), 'assets/help'),
        (str(ROOT / 'output/pdf/help/*.pdf'), 'assets/help'),
        (str(ROOT / 'LICENSE.txt'), '.'),
        (str(ROOT / 'THIRD_PARTY_NOTICES.txt'), '.'),
        (str(ROOT / 'assets' / 'template.html'), 'assets'),
        (str(ROOT / 'assets' / 'caucasus.sqlite'), 'assets'),
        (str(ROOT / 'assets' / 'dcs_airports.sqlite'), 'assets'),
        (str(ROOT / 'assets' / 'helper.html'), 'assets'),
        (str(ROOT / 'assets' / 'map.html'), 'assets'),
        (str(ROOT / 'assets' / 'map.js'), 'assets'),
        (str(ROOT / 'assets' / 'display.js'), 'assets'),
        (str(ROOT / 'assets' / 'airspeed.js'), 'assets'),
        (str(ROOT / 'assets' / 'planner.html'), 'assets'),
        (str(ROOT / 'assets' / 'planner.js'), 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5','PyQt6','PySide2','PySide6'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='C130J_Reference',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / 'assets' / 'C130J.ico'),
)
