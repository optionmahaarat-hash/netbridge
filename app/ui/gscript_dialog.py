from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from app.core import gscript
from app.ui.help_dialog import HelpDialog


class StartWorker(QThread):
    """Checks the script with one real request, then starts the local relay port (network, so off the UI thread)."""
    done = Signal(object)                      # the running GScriptServer or an error text
    def __init__(self, cfg, server, parent=None):
        super().__init__(parent); self.cfg, self.server = cfg, server
    def run(self):
        try:
            relay = gscript.Relay(self.cfg["script_url"], self.cfg["key"], self.cfg["google_ip"], self.cfg["front"])
            relay.test()
            if self.server is not None:
                self.server.stop()
            srv = gscript.GScriptServer(relay)
            srv.start()
            self.done.emit(srv)
        except Exception as e:
            self.done.emit(str(e))


class GScriptDialog(QDialog):
    """Settings + one-time setup of the Google Script relay. `started(server)` is emitted when the local port is running."""
    started = Signal(object)

    def __init__(self, parent=None, server=None):
        super().__init__(parent)
        self.setWindowTitle("Google Script")
        self.resize(640, 380)
        self.server, self.worker = server, None
        cfg = gscript.load_settings()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("A private relay in YOUR Google account. Steps: Copy Code.gs -> paste it at script.google.com -> "
                             "Deploy as Web app (Anyone) -> paste the /exec address here. (Help button: full guide)"))
        form = QFormLayout()
        self.url = QLineEdit(cfg.get("script_url", "")); self.url.setPlaceholderText("https://script.google.com/macros/s/.../exec")
        self.key = QLineEdit(cfg.get("key") or gscript.new_key())
        self.ip = QLineEdit(cfg.get("google_ip", "")); self.ip.setPlaceholderText("optional - a Google IP (empty = automatic)")
        form.addRow("Script address", self.url); form.addRow("Secret key", self.key); form.addRow("Google IP", self.ip)
        lay.addLayout(form)
        r1 = QHBoxLayout()
        for text, fn in (("Copy Code.gs", self.copy_code), ("Open script.google.com", lambda: QDesktopServices.openUrl(QUrl("https://script.google.com"))),
                         ("Install certificate", self.install_cert), ("Help", lambda: HelpDialog(self, "gscript").exec())):
            b = QPushButton(text); b.clicked.connect(fn); r1.addWidget(b)
        lay.addLayout(r1)
        self.msg = QLabel(""); self.msg.setWordWrap(True); lay.addWidget(self.msg)
        self.start_btn = QPushButton("Test and Start"); self.start_btn.setObjectName("primary"); self.start_btn.clicked.connect(self.start)
        lay.addWidget(self.start_btn)

    def copy_code(self):
        try:
            QGuiApplication.clipboard().setText(gscript.code_gs(self.key.text().strip()))
            self.msg.setText("Code.gs copied with your secret key. Paste it into the new Apps Script project.")
        except gscript.GScriptError as e:
            self.msg.setText(str(e))

    def install_cert(self):
        if QMessageBox.question(self, "Google Script",
                "Web pages go through a script that only fetches addresses, so NetBridge opens HTTPS pages on THIS computer with its own "
                "certificate (created here; its key never leaves data/gscript).\n\nAdd that certificate to your Windows user trust list now?\n"
                "Windows will show its own confirmation window.") != QMessageBox.Yes:
            return
        try:
            cert, _ = gscript.ensure_ca()
            gscript.install_ca(cert)
            self.msg.setText("Certificate installed. Firefox needs it imported by hand: " + str(cert))
        except gscript.GScriptError as e:
            self.msg.setText(str(e))

    def start(self):
        if self.worker and self.worker.isRunning():
            return
        try:
            cfg = gscript.check_settings(self.url.text(), self.key.text().strip(), self.ip.text())
        except gscript.GScriptError as e:
            self.msg.setText(str(e)); return
        gscript.save_settings(cfg)
        self.start_btn.setEnabled(False); self.msg.setText("Testing the script with one real request ...")
        self.worker = StartWorker(cfg, self.server, self)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _done(self, result):
        self.start_btn.setEnabled(True)
        if isinstance(result, str):
            self.msg.setText(result); return
        self.server = result
        self.started.emit(result)
        self.accept()
