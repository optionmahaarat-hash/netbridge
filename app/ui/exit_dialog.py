from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QListWidget,
    QListWidgetItem, QCheckBox, QMessageBox, QApplication,
)
from PySide6.QtGui import QShortcut, QKeySequence
from app.core import exitscan


class ExitWorker(QThread):
    result = Signal(int, object)        # index, info or None
    progress = Signal(int, int)

    def __init__(self, exe, items, checks=None, parent=None):
        super().__init__(parent)
        self.exe, self.items, self.checks, self._stop, self.done = exe, items, checks, False, 0

    def stop(self): self._stop = True

    def run(self):
        total = len(self.items)
        def on(key, info):
            self.done += 1
            self.result.emit(key, info); self.progress.emit(self.done, total)
        exitscan.scan_many(self.exe, self.items, on, cancelled=lambda: self._stop, checks=self.checks)


class ExitDialog(QDialog):
    """items: list of (index, profile). After exec(): self.action is None or ('pin', profile_index)."""
    def __init__(self, exe, items, parent=None, group="All", to_uri=None):
        super().__init__(parent)
        self.setWindowTitle("Exit scan - what do websites see for each profile?")
        self.resize(820, 620)
        self.exe, self.items, self.action, self.worker = exe, items, None, None
        self.profiles = dict(items)
        self.to_uri = to_uri
        lay = QVBoxLayout(self)
        help_ = QLabel(
            f"<b>Nothing to type here.</b> Press <b>Start scan</b>. It tests the {len(items)} profile(s) of the group "
            f"'{group}' (change the group in the main window to scan others).<br>"
            "Each profile is started privately and asked: which country / ISP do websites see? and can it open "
            "NotebookLM / Gemini / AI Studio?<br>"
            "<b>What to look for:</b> a line that is NOT 'CLOUDFLARE', in a country such as DE / NL / FI / US, with "
            "<b>OK</b> after NotebookLM / Gemini. Select it and press the green-text button at the bottom.<br>"
            "<b>OK</b> = no block seen. <b>BLOCKED</b> = Google refuses this exit. <b>TIMEOUT / ERR / TLS-ERR</b> = the page could not be loaded "
            "through it at all (slow free server, or it blocks Google): not usable for that site.<br>"
            "If everything is Cloudflare, your list has no useful profile: import other (non-Cloudflare) profiles first "
            "(Subscription / Import file), then scan again. Ctrl+C copies the selected line.")
        help_.setWordWrap(True); help_.setTextFormat(Qt.RichText); lay.addWidget(help_)
        n_cf = sum(1 for _, p in items if exitscan.is_workers(p))
        self.skip_workers = QCheckBox(f"Skip *.workers.dev / *.pages.dev profiles (always Cloudflare) - {n_cf} of {len(items)}")
        self.skip_workers.setChecked(True); lay.addWidget(self.skip_workers)
        self.google = QCheckBox("Also test NotebookLM / Gemini / AI Studio through each exit (slower, shows OK / BLOCKED)")
        self.google.setChecked(True); lay.addWidget(self.google)
        self.hide_cf = QCheckBox("Hide results whose exit is Cloudflare"); self.hide_cf.setChecked(True)
        self.hide_cf.toggled.connect(self.apply_filter); lay.addWidget(self.hide_cf)
        row = QHBoxLayout()
        self.start_btn = QPushButton("Start scan"); self.start_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Stop"); self.stop_btn.clicked.connect(self.stop); self.stop_btn.setEnabled(False)
        row.addWidget(self.start_btn); row.addWidget(self.stop_btn); lay.addLayout(row)
        self.bar = QProgressBar(); lay.addWidget(self.bar)
        self.info = QLabel("Each profile runs in its own private Xray; your current connection is not touched.")
        self.info.setWordWrap(True); lay.addWidget(self.info)
        self.list = QListWidget(); lay.addWidget(self.list)
        self.use_btn = QPushButton("Use selected as the exit for Google AI sites (Gemini, NotebookLM, AI Studio)")
        self.use_btn.clicked.connect(self.use); lay.addWidget(self.use_btn)
        row3 = QHBoxLayout()
        cb = QPushButton("Copy visible results"); cb.clicked.connect(self.copy_all); row3.addWidget(cb)
        cl = QPushButton("Copy config link of selected"); cl.clicked.connect(self.copy_link); row3.addWidget(cl)
        lay.addLayout(row3)
        QShortcut(QKeySequence.Copy, self.list, activated=self.copy_selected)
        lay.addWidget(QLabel("Then open the site with 'Open clean browser'. Free servers are shared and unstable; "
                             "do not log in to important accounts through servers you do not trust."))

    def start(self):
        items = [(i, p) for i, p in self.items if not (self.skip_workers.isChecked() and exitscan.is_workers(p))]
        if not items:
            QMessageBox.information(self, "Exit scan", "Nothing to scan."); return
        self.list.clear(); self.bar.setValue(0); self.bar.setMaximum(len(items))
        self.worker = ExitWorker(self.exe, items, exitscan.GOOGLE_CHECKS if self.google.isChecked() else None, self)
        self.worker.result.connect(self.on_result); self.worker.progress.connect(lambda d, t: self.bar.setValue(d))
        self.worker.finished.connect(self.on_finished)
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.info.setText("Scanning ..."); self.worker.start()

    def stop(self):
        if self.worker: self.worker.stop()
        self.stop_btn.setEnabled(False)

    def on_result(self, idx, info):
        if not info:                                   # dead profiles are not listed
            return
        p = self.profiles[idx]
        it = QListWidgetItem(f"{exitscan.describe(info)}     |  {p.get('name', '?')}")
        it.setData(Qt.UserRole, idx); it.setData(Qt.UserRole + 1, bool(info.get("cloudflare")))
        self.list.addItem(it)
        it.setHidden(self.hide_cf.isChecked() and bool(info.get("cloudflare")))

    def apply_filter(self, _=None):
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(self.hide_cf.isChecked() and bool(it.data(Qt.UserRole + 1)))

    def on_finished(self):
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        shown = sum(1 for i in range(self.list.count()) if not self.list.item(i).isHidden())
        self.info.setText(f"Done: {self.list.count()} profile(s) answered, {shown} shown." +
                          ("" if shown else " Every profile that answered exits through Cloudflare (or none answered). Import non-Cloudflare profiles "
                          "(Subscription / Import file) and scan again."))

    def _visible(self):
        return [self.list.item(i) for i in range(self.list.count()) if not self.list.item(i).isHidden()]

    def copy_all(self):
        QApplication.clipboard().setText("\n".join(it.text() for it in self._visible()))
        self.info.setText(f"Copied {len(self._visible())} line(s).")

    def copy_selected(self):
        it = self.list.currentItem()
        if it: QApplication.clipboard().setText(it.text())

    def copy_link(self):
        it = self.list.currentItem()
        if not it or not self.to_uri:
            QMessageBox.information(self, "Exit scan", "Select a result first."); return
        QApplication.clipboard().setText(self.to_uri(self.profiles[it.data(Qt.UserRole)]))
        self.info.setText("Config link copied.")

    def use(self):
        it = self.list.currentItem()
        if not it or it.isHidden():
            QMessageBox.information(self, "Exit scan", "Select a result first."); return
        self.action = ("pin", it.data(Qt.UserRole)); self.accept()

    def done(self, r):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.worker.wait(8000)
        super().done(r)
