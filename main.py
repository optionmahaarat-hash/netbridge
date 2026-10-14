import os
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.ui.icon import app_icon
from app.ui.main_window import MainWindow

if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)     # data/, configs/ and cores/ are relative: works from any start folder
    if sys.platform == "win32":
        try:   # own identity: the taskbar shows the NetBridge icon (and groups windows) instead of python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AppBaz.NetBridge")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("NetBridge")
    app.setWindowIcon(app_icon())      # every window and dialog inherits it
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
