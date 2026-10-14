"""Where things live. Frozen (PyInstaller) -> next to NetBridgeLite.exe; otherwise the project folder."""
import os, sys
from pathlib import Path


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if frozen() else Path(__file__).resolve().parents[2]


def xray_exe() -> Path:
    return app_dir() / "cores" / "xray" / ("xray.exe" if os.name == "nt" else "xray")


def exe_name() -> str:
    return Path(sys.executable).name if frozen() else "NetBridgeLite.exe"
