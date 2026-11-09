# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('web', 'web'), ('mods', 'mods'), ('riven.ico', '.')]
binaries = []
hiddenimports = ['keyring.backends.Windows']
hiddenimports += collect_submodules('keyring')
tmp_ret = collect_all('minecraft_launcher_lib')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
for _pkg in ('webview', 'clr_loader', 'pythonnet'):
    _r = collect_all(_pkg)
    datas += _r[0]; binaries += _r[1]; hiddenimports += _r[2]


a = Analysis(
    ['riven.py'],
    pathex=[],
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
    [],
    exclude_binaries=True,
    name='RivenLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['riven.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='RivenLauncher',
)
