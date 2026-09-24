# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller yapilandirmasi - onedir Windows dagitimi.

onedir secildi (onefile degil):
* Acilis suresi belirgin daha kisa; onefile her caliştirmada gecici
  klasore acar ve 150+ MB Qt yukunu her seferinde kopyalar.
* Antivirus/SmartScreen onedir'e daha az takilir.
* Inno Setup zaten dosyalari kendi kuracagi icin tek dosya avantaji yok.

Calistirma:
    .venv/Scripts/python -m PyInstaller packaging/LumaAtelier.spec --noconfirm
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
RESOURCES = ROOT / "resources"

sys.path.insert(0, str(SRC))
from luma_atelier.core.branding import APP_SLUG, APP_VERSION  # noqa: E402

# Kullanilmayan Qt modulleri paketten cikarilir. Bunlar olmadan
# dagitim ~150 MB kucuk kalir ve tarama suresi duser.
EXCLUDED_QT = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSerialPort",
    "PySide6.QtSerialBus", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtSensors", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtHelp",
    "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQml",
    "PySide6.QtQuickControls2", "PySide6.QtHttpServer", "PySide6.QtGraphs",
]

EXCLUDED_OTHER = [
    "tkinter", "unittest", "pydoc_data", "test", "distutils",
    "matplotlib", "scipy", "pandas", "IPython", "notebook",
    "setuptools", "pip", "wheel", "pytest", "_pytest",
]

datas = [
    (str(RESOURCES), "resources"),
]

hiddenimports = [
    "luma_atelier",
    *collect_submodules("luma_atelier"),
    # tifffile sikistirma kodeklerini calisma aninda ice aktarir
    "imagecodecs",
    "imagecodecs._shared",
]

a = Analysis(
    [str(SRC / "luma_atelier" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_QT + EXCLUDED_OTHER,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_SLUG,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX antivirus yanlis pozitiflerini artirir
    console=False,      # acilista siyah terminal penceresi olmasin
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(RESOURCES / "icons" / "app.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_SLUG,
)
