import json
import time
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from app.core import tg_proxy

SAVE = Path("data/tg_proxy.json")          # the link and its secrets (NEVER the Cloudflare token)


def load_saved():
    try:
        d = json.loads(SAVE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and d.get("link") else None
    except (OSError, ValueError):
        return None


def save(d):
    try:
        SAVE.parent.mkdir(parents=True, exist_ok=True)
        SAVE.write_text(json.dumps(d, indent=1), encoding="utf-8")
    except OSError:
        pass


class ZonesWorker(QThread):
    done = Signal(object)                      # list of (zone_id, name) or an error text
    def __init__(self, token, parent=None):
        super().__init__(parent); self.token = token
    def run(self):
        try:
            self.done.emit(tg_proxy.list_zones(self.token))
        except Exception as e:
            self.done.emit(str(e))


class CreateWorker(QThread):
    """Downloads the Worker, deploys it with fresh secrets and checks /health (network, so off the UI thread)."""
    status = Signal(str)
    done = Signal(object)                      # result dict (with 'health') or an error text
    def __init__(self, token, zone, label, proxy, parent=None):
        super().__init__(parent); self.token, self.zone, self.label, self.proxy = token, zone, label, proxy
    def run(self):
        try:
            self.status.emit("Downloading the Telegram proxy Worker from its repository ...")
            src = tg_proxy.fetch_source(self.proxy)
            r = tg_proxy.deploy(self.token, src, zone=self.zone, label=self.label, progress=self.status.emit)
            ok, text = False, ""
            for i in range(4):                                   # a new Worker / domain needs a little time before it answers
                self.status.emit(f"Checking https://{r['server']}/health ({i + 1}/4) ...")
                ok, text = tg_proxy.health(r["server"], self.proxy)
                if ok:
                    break
                time.sleep(8)
            r["health"] = (ok, text)
            self.done.emit(r)
        except Exception as e:
            self.done.emit(str(e))


class TgProxyDialog(QDialog):
    """Makes a Telegram web proxy on the user's own Cloudflare account. `proxy` = NetBridge's local HTTP proxy when connected."""
    def __init__(self, parent=None, proxy=None):
        super().__init__(parent)
        self.setWindowTitle("Telegram proxy (your own Cloudflare Worker)")
        self.resize(660, 520)
        self.proxy, self.worker, self.zw = proxy, None, None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Makes a Telegram 'web proxy' on YOUR free Cloudflare account with the open-source Worker ToiCF/CF-Workers-TGProxy "
            "(GPL-3.0; downloaded from its repository now, not part of NetBridge).\n\n"
            "1) dash.cloudflare.com > My Profile > API Tokens > Create Token > 'Edit Cloudflare Workers' template. Paste it below "
            "(used once, never saved).\n"
            "2) A workers.dev address is often filtered. For a stable link add a domain you own to Cloudflare first, then pick it here."))
        form = QFormLayout()
        self.token = QLineEdit(); self.token.setEchoMode(QLineEdit.Password); self.token.setPlaceholderText("Cloudflare API token")
        form.addRow("API token:", self.token)
        row = QHBoxLayout()
        self.zones = QComboBox(); self.zones.addItem("(no custom domain - workers.dev address only)", None)
        self.load_btn = QPushButton("Load my domains"); self.load_btn.clicked.connect(self.load_zones)
        row.addWidget(self.zones, 1); row.addWidget(self.load_btn)
        form.addRow("Domain:", row)
        self.label = QLineEdit("tg"); self.label.setPlaceholderText("sub-domain, e.g. tg  (empty = the domain itself)")
        form.addRow("Sub-domain:", self.label)
        lay.addLayout(form)
        self.go = QPushButton("Create the proxy"); self.go.setObjectName("primary"); self.go.clicked.connect(self.create)
        lay.addWidget(self.go)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(200)
        lay.addWidget(self.log, 1)
        lay.addWidget(QLabel("Your Telegram link (open it in Telegram, or send it to others):"))
        self.link = QLineEdit(); self.link.setReadOnly(True)
        lay.addWidget(self.link)
        br = QHBoxLayout()
        self.copy_btn = QPushButton("Copy link"); self.copy_btn.clicked.connect(self.copy)
        self.open_btn = QPushButton("Open link"); self.open_btn.clicked.connect(self.open_link)
        br.addWidget(self.copy_btn); br.addWidget(self.open_btn)
        lay.addLayout(br)
        saved = load_saved()
        if saved:
            self.link.setText(saved["link"])
            self.log.appendPlainText(f"Saved proxy: {saved.get('server', '')} (press 'Create the proxy' to make a new one).")
        self._buttons()

    def _buttons(self):
        has = bool(self.link.text())
        self.copy_btn.setEnabled(has); self.open_btn.setEnabled(has)

    def load_zones(self):
        t = self.token.text().strip()
        if not t:
            QMessageBox.information(self, "Telegram proxy", "Paste the API token first."); return
        self.load_btn.setEnabled(False)
        self.zw = ZonesWorker(t, self); self.zw.done.connect(self._zones); self.zw.start()

    def _zones(self, result):
        self.load_btn.setEnabled(True)
        if not isinstance(result, list):
            QMessageBox.warning(self, "Telegram proxy", str(result)); return
        while self.zones.count() > 1:
            self.zones.removeItem(1)
        for zid, name in result:
            self.zones.addItem(name, (zid, name))
        self.log.appendPlainText(f"{len(result)} domain(s) found on the account." if result else
                                 "No active domain on this account yet (add one in Cloudflare first, or use the workers.dev address).")

    def create(self):
        if self.worker and self.worker.isRunning():
            return
        t = self.token.text().strip()
        if not t:
            QMessageBox.information(self, "Telegram proxy", "Paste the API token first."); return
        zone = self.zones.currentData()
        self.go.setEnabled(False)
        self.worker = CreateWorker(t, zone, self.label.text(), self.proxy, self)
        self.worker.status.connect(self.log.appendPlainText)
        self.worker.done.connect(self._created)
        self.worker.start()

    def _created(self, r):
        self.go.setEnabled(True)
        if not isinstance(r, dict):
            self.log.appendPlainText("Failed: " + str(r))
            QMessageBox.warning(self, "Telegram proxy", str(r)); return
        ok, text = r["health"]
        self.link.setText(r["link"])
        save({k: r[k] for k in ("name", "secret", "boot", "server", "domain", "workers_host", "link")})
        self.log.appendPlainText(f"Created: {r['server']}")
        if ok:
            self.log.appendPlainText("Health check: OK. Open the link in Telegram and press Connect (the first connection takes 10-20 seconds).")
        else:
            self.log.appendPlainText(f"Health check did not pass yet ({text}). A new domain can take a few minutes; try the link later. "
                                     "If it never connects the domain may be filtered: use another domain or sub-domain.")
        self._buttons()

    def copy(self):
        QGuiApplication.clipboard().setText(self.link.text())
        self.log.appendPlainText("Link copied.")

    def open_link(self):
        QDesktopServices.openUrl(QUrl(self.link.text()))
