# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files

sys.setrecursionlimit(sys.getrecursionlimit() * 5)

# ---------------------------------------------------------------------------
# Windows icon: generate assets/MyIcon.ico from assets/AppIcon.png if missing.
# Pillow is a runtime dependency (pyproject.toml), so this is safe.
# ---------------------------------------------------------------------------
if sys.platform == 'win32' and not os.path.exists('assets/MyIcon.ico'):
    try:
        from PIL import Image
        Image.open('assets/AppIcon.png').save(
            'assets/MyIcon.ico',
            format='ICO',
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    except Exception as exc:
        print(f"[FittingApp.spec] Could not generate MyIcon.ico: {exc}")

# ---------------------------------------------------------------------------
# Per-platform icon resolution
# ---------------------------------------------------------------------------
icon_file = None
if sys.platform == 'darwin' and os.path.exists('assets/MyIcon.icns'):
    icon_file = 'assets/MyIcon.icns'
elif sys.platform == 'win32' and os.path.exists('assets/MyIcon.ico'):
    icon_file = 'assets/MyIcon.ico'

# ---------------------------------------------------------------------------
# Bundled data files: demo/example datasets + package data for pint & pyqtgraph
# ---------------------------------------------------------------------------
datas = [
    ('data/IDA_system.txt', 'data'),
    ('data/DBA_system_host_to_dye.txt', 'data'),
    ('data/GDA_system.txt', 'data'),
    ('data/Dye_alone.txt', 'data'),
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
    'PIL.ImageTk',
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
    name='FittingApp',
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
    name='FittingApp',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='FittingApp.app',
        icon=icon_file,
        bundle_identifier='com.suprasense.fittingapp',
        info_plist={
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '11.0',
            'CFBundleShortVersionString': '0.1.0',
        },
    )
