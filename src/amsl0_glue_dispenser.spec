# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Include PyQt5 and matplotlib in hidden imports
hidden_imports = [
    'pkg_resources.extern',
    'PyQt5',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'matplotlib',
    'matplotlib.backends.backend_qt5agg',  # Required for PyQt5 backend
]

# Collect data files for PyQt5 and matplotlib
datas = collect_data_files('PyQt5') + collect_data_files('matplotlib')

a = Analysis(
    ['amsl0_glue_dispenser.py'],
    pathex=[],
    binaries=[],
    datas=datas,  # Include collected data files
    hiddenimports=hidden_imports,  # Include hidden imports
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'
)