# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for VisOPU — TL.0009 PAN-TILT Control Application."""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

ROOT = Path(SPECPATH)

# Collect all ultralytics data files (configs, YAMLs, etc.)
ultralytics_datas = []
try:
    ultralytics_datas = collect_data_files('ultralytics')
except Exception:
    pass

# Collect cv2 data files (needed for OpenCV)
cv2_datas = []
try:
    cv2_datas = collect_data_files('cv2')
except Exception:
    pass

# Collect onvif-zeep WSDL files (required for ONVIF zoom/focus/PTZ in exe)
# NOTE: The WSDL XML files are NOT inside the onvif package — they live in a
# separate 'wsdl/' directory at the site-packages root level.
# ONVIFCamera.__init__ resolves: os.path.dirname(os.path.dirname(onvif.__file__)) + '/wsdl'
# In frozen mode that becomes _MEIPASS/wsdl/, so we place them at dest 'wsdl'.
onvif_datas = []
try:
    onvif_datas = collect_data_files('onvif')
except Exception:
    pass

# Explicitly add the site-packages/wsdl directory (33 WSDL/XSD files for ONVIF)
import onvif as _onvif_pkg
_wsdl_src = str(Path(_onvif_pkg.__file__).resolve().parent.parent / 'wsdl')
wsdl_data = [(_wsdl_src, 'wsdl')]  # dest=wsdl → _MEIPASS/wsdl/

# Collect zeep data files (SOAP/XML schemas used by onvif-zeep)
zeep_datas = []
try:
    zeep_datas = collect_data_files('zeep')
except Exception:
    pass

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # YOLO model weights
        (str(ROOT / 'yolov8n.pt'), '.'),
        (str(ROOT / 'yolov8m.pt'), '.'),
        # App package (Python files are auto-collected, but include non-py assets)
        (str(ROOT / 'app'), 'app'),
        # Data directory (offline map tiles, etc.)
        (str(ROOT / 'data'), 'data'),
        # Ultralytics + OpenCV + ONVIF/zeep data files
        *ultralytics_datas,
        *cv2_datas,
        *onvif_datas,
        *zeep_datas,
        *wsdl_data,
    ],
    hiddenimports=[
        # PyQt6 modules
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtNetwork',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebChannel',
        # ML / CV
        'ultralytics',
        'ultralytics.nn',
        'ultralytics.nn.tasks',
        'ultralytics.engine',
        'ultralytics.trackers',
        'numpy',
        'cv2',
        # ONVIF / SOAP
        'onvif',
        'onvif.client',
        'onvif.definition',
        'onvif.exceptions',
        'zeep',
        'zeep.client',
        'lxml',
        'lxml.etree',
        'lxml.objectify',
        # App modules
        'app',
        'app.mainwindow',
        'app.communicators',
        'app.detector',
        'app.offline_map',
        'app.styles',
        'app.widgets',
    ] + collect_submodules('ultralytics'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'notebook',
        'pytest',
        'tkinter',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VisOPU',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # Windowed app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VisOPU',
)
