# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('E:/Android/PM/pdfEditor/assets', 'assets')]
datas += collect_data_files('pymupdf')


a = Analysis(
    ['E:/Android/PM/pdfEditor/app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['PySide6.QtSvg', 'pymupdf', 'pdf2docx', 'docx', 'win32com', 'pythoncom', 'comtypes'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pymupdf.layout', 'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtSql', 'PySide6.QtNetwork', 'PySide6.QtTest', 'PySide6.QtBluetooth', 'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtPositioning', 'PySide6.QtWebChannel', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.Qt3DCore', 'tkinter', 'matplotlib', 'scipy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
splash = Splash(
    'E:/Android/PM/pdfEditor/assets/splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    minify_script=True,
    always_on_top=True,
    center='primary',
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    [],
    exclude_binaries=True,
    name='PdfEditor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['E:/Android/PM/pdfEditor/assets/app.ico'],
    manifest='E:/Android/PM/pdfEditor/app.manifest',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    splash.binaries,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PdfEditor',
)
