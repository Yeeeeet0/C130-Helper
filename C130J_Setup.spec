# Rebuild the application before this installer so its payload is current.
from pathlib import Path
ROOT=Path(SPECPATH)
a=Analysis([str(ROOT/'src/installer.py')],pathex=[str(ROOT/'src')],
           binaries=[],datas=[(str(ROOT/'build/installer/payload'),'payload')],
           hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],
           excludes=['webview','clr','pythonnet','PyQt5','PyQt6','PySide2','PySide6'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='C130J_CDU_Helper_Setup',
        debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
        console=False,icon=str(ROOT/'assets/C130J.ico'))
