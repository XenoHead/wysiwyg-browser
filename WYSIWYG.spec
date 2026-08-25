# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('app.js', '.'), ('fyrlogo.png', '.'), ('index.html', '.'), ('editor.html', '.'), ('admin.html', '.'), ('search.html', '.'), ('style_guide.html', '.'), ('data.json', '.'), ('media_formats.json', '.'), ('version.json', '.'), ('changelog.txt', '.'), ('styles.css', '.'), ('walmart.html', '.'), ('fyrlogo.ico', '.'), ('fyr-sign-front.png', '.'), ('Uberpaste', 'Uberpaste'), ('WysiScan', 'WysiScan'), ('WalmartSheet', 'WalmartSheet'), ('Adds', 'Adds'), ('.env', '.'), ('C:/Git/Xeno_ui', 'Xeno_ui')],
    hiddenimports=['psutil', 'win32timezone', 'webview', 'pytesseract', 'cv2', 'PIL', 'pyperclip', 'Xeno_ui.about', 'Xeno_ui.theme'],
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
    [],
    exclude_binaries=True,
    name='WYSIWYG',
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
    icon=['fyrlogo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WYSIWYG',
)
