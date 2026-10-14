from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from app.ui.icon import app_icon, logo_pixmap
from app.version import VERSION


class AboutDialog(QDialog):
    def __init__(self, parent=None, version=VERSION, name="NetBridge"):
        super().__init__(parent)
        self.setWindowTitle(name)
        self.setWindowIcon(app_icon())
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignHCenter)
        pic = QLabel(); pic.setPixmap(logo_pixmap("logo.png", 220)); pic.setAlignment(Qt.AlignCenter)
        lay.addWidget(pic)
        info = QLabel(f"<h2 style='margin:0'>{name}</h2>Version {version}<br>by AppBaz<br>"
                      f"<span style='color:gray'>Your network bridge</span>")
        info.setAlignment(Qt.AlignCenter)
        lay.addWidget(info)
        ok = QPushButton("OK"); ok.clicked.connect(self.accept); lay.addWidget(ok)
