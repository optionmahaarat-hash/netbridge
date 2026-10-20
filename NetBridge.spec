# PyInstaller recipe for the FULL NetBridge (one folder: NetBridge.exe + _internal\). Built by build_full.bat / the GitHub workflow
import sys
from pathlib import Path

root = Path(SPECPATH)
# assets without the 1.5 MB source artwork
assets = [(str(f), str(Path("assets") / f.relative_to(root / "assets").parent))
          for f in (root / "assets").rglob("*") if f.is_file() and "source" not in f.relative_to(root / "assets").parts]

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    datas=assets,
    hiddenimports=["aioquic.quic.connection", "aioquic.quic.configuration", "aioquic.quic.events",
                   "cryptography.hazmat.primitives.asymmetric.ed25519"],
    excludes=["tkinter", "numpy", "PIL", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts"],
    noarchive=False,
)
# Qt parts a Widgets app never uses (the software OpenGL DLL alone is ~20 MB on Windows)
BLOCK = ("qt6pdf", "qt6quick", "qt6qml", "qt6virtualkeyboard", "opengl32sw", "qt6designer", "qt6labs")
a.binaries = [b for b in a.binaries if not any(x in b[0].lower().replace("\\", "/").split("/")[-1] for x in BLOCK)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="NetBridge",
    console=False,                                   # no black window
    icon=str(root / "assets" / "netbridge.ico") if sys.platform == "win32" else None,
    upx=False,                                       # UPX makes antivirus false alarms much more likely
)
coll = COLLECT(exe, a.binaries, a.datas, name="NetBridge", upx=False)
