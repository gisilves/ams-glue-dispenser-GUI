# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_submodules

# Collect hidden imports for PyQt5 and Matplotlib
hiddenimports = collect_submodules('PyQt5') + collect_submodules('matplotlib') + ['pkg_resources.extern', 'PyQt5']

a = Analysis(
    ['amsl0_glue_dispenser.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports + ['pkg_resources.extern'],  # Add necessary hidden imports
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='amsl0_glue_dispenser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False if you don't want a console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'
)
