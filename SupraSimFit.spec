# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files

# Single source of truth for the app version (also read by the GUI and
# the auto-tag workflow). Lives at the repo root. PyInstaller execs this
# spec without the repo root on sys.path, so add it (SPECPATH is the spec's
# directory, injected by PyInstaller) before importing.
sys.path.insert(0, SPECPATH)
from _version import __version__

sys.setrecursionlimit(sys.getrecursionlimit() * 5)

# ---------------------------------------------------------------------------
# Per-platform icon resolution
# ---------------------------------------------------------------------------
icon_file = None
if sys.platform == 'darwin' and os.path.exists('assets/MyIcon.icns'):
    icon_file = 'assets/MyIcon.icns'
elif sys.platform == 'win32' and os.path.exists('assets/AppIcon.ico'):
    icon_file = 'assets/AppIcon.ico'

# ---------------------------------------------------------------------------
# Bundled data files: demo/example datasets, runtime icon assets, and
# package data for pint & pyqtgraph.
# ---------------------------------------------------------------------------
datas = [
    ('data/IDA_system.txt', 'data'),
    ('data/DBA_system_host_to_dye.txt', 'data'),
    ('data/GDA_system.txt', 'data'),
    ('data/Dye_alone.txt', 'data'),
    ('assets/AppIcon.ico', 'assets'),
    ('assets/AppIcon.png', 'assets'),
]
datas += collect_data_files('pint')
datas += collect_data_files('pyqtgraph')

# ---------------------------------------------------------------------------
# Hidden imports: modules PyInstaller's static analyzer misses
# (lazy imports, dynamic dispatch, scipy submodules, etc.)
# ---------------------------------------------------------------------------
hiddenimports = [
    'openpyxl',
    'pint',
    'pyqtgraph.exporters',
    'pyqtgraph.parametertree',
    'scipy.optimize',
    'scipy.optimize._minimize',
    'scipy.special',
]

# ---------------------------------------------------------------------------
# Excludes: stale or unused modules that would otherwise bloat the bundle
# ---------------------------------------------------------------------------
excludes = [
    'tkinter', '_tkinter',
    'matplotlib',
    'PyQt5', 'PySide2', 'PySide6',
    'PIL', 'PIL.ImageTk',
]

a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SupraSimFit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SupraSimFit',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='SupraSimFit.app',
        icon=icon_file,
        bundle_identifier='com.suprasense.suprasimfit',
        info_plist={
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '11.0',
            'CFBundleShortVersionString': __version__,
            'CFBundleVersion': __version__,
        },
    )
