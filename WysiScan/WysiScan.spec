# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:/Git/WysiWyg-Browser/WysiScan/scanner_test.html', 'WysiScan'), ('C:/Git/WysiWyg-Browser/WysiScan/WysiScan.ico', 'WysiScan'), ('C:/Git/WysiWyg-Browser/WysiScan/WysiScan.png', 'WysiScan'), ('C:/Git/WysiWyg-Browser/WysiScan/imageconvert/app.py', 'imageconvert'), ('C:/Git/WysiWyg-Browser/WysiScan/imageconvert/config.json', 'imageconvert'), ('C:/Git/WysiWyg-Browser/WysiScan/imageconvert/index.html', 'imageconvert'), ('C:/Git/WysiWyg-Browser/WysiScan/imageconvert/script.js', 'imageconvert'), ('C:/Git/WysiWyg-Browser/WysiScan/imageconvert/styles.css', 'imageconvert'), ('C:/Git/WysiWyg-Browser/WysiScan/imageconvert/assets/css', 'imageconvert/assets/css'), ('C:/Git/WysiWyg-Browser/WysiScan/imageconvert/assets/webfonts', 'imageconvert/assets/webfonts'), ('C:/Git/WysiWyg-Browser/WysiScan/config.json', '.')]
binaries = []
hiddenimports = ['tkinter', 'gemini_pool', 'webview', 'clr', 'clr_loader']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:/Git/WysiWyg-Browser/WysiScan/scanner_server.py'],
    pathex=['..'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WysiScan',
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
    icon=['C:/Git/WysiWyg-Browser/WysiScan/WysiScan.ico'],
)
