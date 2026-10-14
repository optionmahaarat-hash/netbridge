import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "assets"

def test_assets_exist_and_ico_has_all_sizes():
    for f in ("logo.png", "mark.png", "netbridge.ico"):
        assert (A / f).exists(), f
    sizes = Image.open(A / "netbridge.ico").ico.sizes()
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(sizes)

def test_logo_has_transparent_corners_and_opaque_center():
    im = Image.open(A / "logo.png").convert("RGBA")
    w, h = im.size
    assert im.getpixel((2, 2))[3] == 0 and im.getpixel((w - 3, h - 3))[3] == 0
    assert im.getpixel((w // 2, h // 2))[3] == 255

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])

def test_app_icon_has_every_size(qapp):
    from app.ui.icon import app_icon
    ic = app_icon()
    assert not ic.isNull()
    assert {16, 32, 48, 256} <= {s.width() for s in ic.availableSizes()}

def test_main_window_and_about_use_icon(qapp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                       # keep data/ and configs/ out of the project
    from app.ui.main_window import MainWindow
    from app.ui.about_dialog import AboutDialog
    from app.version import VERSION
    w = MainWindow()
    assert not w.windowIcon().isNull() and VERSION in w.windowTitle()
    help_menu = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Help")
    assert [a.text().replace("&", "") for a in help_menu.actions()] == ["About NetBridge"]
    d = AboutDialog(w)
    assert not d.windowIcon().isNull()
