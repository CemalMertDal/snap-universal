# PyInstaller build recipe. Run through scripts/build.ps1.
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = [("assets", "assets")]
datas += collect_data_files("mediapipe", excludes=["**/*.pyc", "**/testdata/**"])
datas += collect_data_files("qfluentwidgets")
binaries = collect_dynamic_libs("mediapipe")

a = Analysis(
    ["snap/__main__.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=["snap.selftest", "snap.ui.app"],
    excludes=["tkinter", "matplotlib", "scipy", "PIL", "pytest", "IPython", "pandas",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf",
              "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    noarchive=False,
)

# Big binaries the app never loads: FFmpeg video I/O (we read cameras through DirectShow),
# the software OpenGL fallback, and Qt Quick/QML/PDF pulled in by generic Qt plugins.
_UNUSED = ("opencv_videoio_ffmpeg", "opengl32sw", "qt6quick", "qt6qml", "qt6pdf", "qpdf",
           "qt6virtualkeyboard", "qt6opengl", "qt6network")
a.binaries = [b for b in a.binaries if not any(u in b[0].lower().replace("\\", "/").split("/")[-1]
                                               for u in _UNUSED)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Snap",
    icon="assets/icon.ico",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Snap")
