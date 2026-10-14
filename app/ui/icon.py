"""Icons and logo images (assets/ is built by tools/make_icons.py)."""
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap


def asset_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))   # works when frozen too
    return base / "assets"


def app_icon() -> QIcon:
    """All sizes 16..256: Qt/Windows picks the sharpest one for title bar, taskbar, Alt-Tab."""
    icon = QIcon()
    for f in sorted((asset_dir() / "icons").glob("netbridge-*.png")):
        icon.addFile(str(f))
    return icon


def logo_pixmap(name="mark.png", size=40) -> QPixmap:
    """Pixmap that is crisp on HiDPI screens; `size` is in logical pixels."""
    screen = QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    pm = QPixmap(str(asset_dir() / name)).scaled(int(size * dpr), int(size * dpr),
                                                 Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    return pm
