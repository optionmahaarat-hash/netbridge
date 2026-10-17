from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QTextBrowser

from app.ui import help_text


class HelpDialog(QDialog):
    """Left: list of topics. Right: the text. `start` selects a topic by key."""
    def __init__(self, parent=None, start="start"):
        super().__init__(parent)
        self.setWindowTitle("راهنما / Help")
        self.resize(900, 620)
        lay = QHBoxLayout(self)
        self.list = QListWidget(); self.list.setMaximumWidth(250)
        self.view = QTextBrowser(); self.view.setLayoutDirection(Qt.RightToLeft); self.view.setOpenExternalLinks(True)
        lay.addWidget(self.list); lay.addWidget(self.view, 1)
        for key, title, _ in help_text.TOPICS:
            self.list.addItem(title)
        self.list.currentRowChanged.connect(lambda i: self.view.setHtml(help_text.TOPICS[i][2]) if i >= 0 else None)
        self.list.setCurrentRow(next((i for i, t in enumerate(help_text.TOPICS) if t[0] == start), 0))
