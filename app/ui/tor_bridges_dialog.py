import json
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout)

from app.core import aether

SAVE = Path("data/tor_bridges.json")


def load():
    """(bridge lines, go-to-bridges-at-once flag) saved earlier."""
    try:
        d = json.loads(SAVE.read_text(encoding="utf-8"))
        return [str(x) for x in d.get("bridges", [])], bool(d.get("now"))
    except (OSError, ValueError, AttributeError):
        return [], False


def save(bridges, now):
    try:
        SAVE.parent.mkdir(parents=True, exist_ok=True)
        SAVE.write_text(json.dumps({"bridges": bridges, "now": bool(now)}, indent=1), encoding="utf-8")
    except OSError:
        pass


class TorBridgesDialog(QDialog):
    """Own Tor bridge lines for the 'Tor alone' / 'Tor via WARP' buttons. Empty = Aether fetches bridges by itself."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tor bridges")
        self.resize(640, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "When Tor is blocked, a bridge you get yourself often still works.\n"
            "Get lines at bridges.torproject.org (Get Bridges), by email to bridges@torproject.org (from Gmail/Riseup), or from the "
            "Telegram bot @GetBridgesBot - or ask a friend abroad to send them.\n"
            "Paste one bridge per line (obfs4 / snowflake / webtunnel ...). Leave empty to let Aether find bridges itself."))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("obfs4 192.0.2.55:38114 316E643333645F6D79216558614D3931657A5F5F cert=... iat-mode=0")
        lay.addWidget(self.text, 1)
        self.now = QCheckBox("Use bridges at once (skip trying plain Tor first - faster when Tor is blocked)")
        lay.addWidget(self.now)
        row = QHBoxLayout()
        ok = QPushButton("Save"); ok.setObjectName("primary"); ok.clicked.connect(self.accept_)
        no = QPushButton("Cancel"); no.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(no); row.addWidget(ok)
        lay.addLayout(row)
        b, n = load()
        self.text.setPlainText("\n".join(b)); self.now.setChecked(n)
        self.result_bridges, self.result_now = b, n

    def accept_(self):
        good, bad = aether.parse_bridges(self.text.toPlainText())
        if bad:
            QMessageBox.warning(self, "Tor bridges", "These lines do not look like bridges and were skipped:\n\n" + "\n".join(bad[:6]))
        save(good, self.now.isChecked())
        self.result_bridges, self.result_now = good, self.now.isChecked()
        self.accept()
