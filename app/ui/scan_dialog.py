from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton, QProgressBar, QCheckBox,
    QListWidget, QListWidgetItem, QApplication, QMessageBox,
)
from app.core import ipscan


class ScanWorker(QThread):
    found = Signal(str, int, str)       # ip, ms, colo
    progress = Signal(int, int)         # done, total

    def __init__(self, count, port, sni, parent=None, ipv6=False):
        super().__init__(parent)
        self.count, self.port, self.sni, self.ipv6 = count, port, sni, ipv6
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        ranges = ipscan.load_ranges()
        if self.ipv6:
            ranges = ranges + ipscan.load_ranges6()          # half of the IPs are IPv6 (see ipscan.sample_ips)
        ips = ipscan.sample_ips(ranges, self.count)
        ipscan.scan(ips, self.port, self.sni,
                    on_result=lambda ip, ms, colo: self.found.emit(ip, ms, colo),
                    on_progress=lambda d, t: self.progress.emit(d, t),
                    cancelled=lambda: self._stop)


class ScanDialog(QDialog):
    """Finds Cloudflare IPs that work from your ISP for the selected profile.
    After exec(): self.action is None, ("one", ip) or ("many", [ips])."""

    def __init__(self, profile, n_cf_profiles, parent=None, group=""):
        super().__init__(parent)
        self.setWindowTitle("Clean IP scanner (Cloudflare)")
        self.resize(560, 560)
        self.action = None
        self.worker = None
        self.port, self.sni = ipscan.scan_target(profile)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Profile: {profile.get('name', '?')}\nTest target:  SNI / Host = {self.sni or '(none)'}   port = {self.port}"))
        if not ipscan.looks_cloudflare(profile):
            w = QLabel("This profile does not look like a Cloudflare config (TLS on a Cloudflare port). "
                       "The scan only makes sense for Workers / Pages / Cloudflare-CDN profiles.")
            w.setWordWrap(True); w.setStyleSheet("color:#FFB020"); lay.addWidget(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("IPs to test:"))
        self.count = QSpinBox(); self.count.setRange(20, 3000); self.count.setValue(300); self.count.setSingleStep(100)
        row.addWidget(self.count)
        self.v6 = QCheckBox("Include IPv6")
        ok6 = ipscan.has_ipv6()
        self.v6.setChecked(ok6); self.v6.setEnabled(ok6)
        self.v6.setToolTip("Half of the tested IPs are IPv6." if ok6 else "This computer has no IPv6 route to the internet.")
        row.addWidget(self.v6); row.addStretch()
        self.start_btn = QPushButton("Start scan"); self.start_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Stop"); self.stop_btn.clicked.connect(self.stop); self.stop_btn.setEnabled(False)
        row.addWidget(self.start_btn); row.addWidget(self.stop_btn)
        lay.addLayout(row)
        self.bar = QProgressBar(); lay.addWidget(self.bar)
        self.info = QLabel("Scan uses your normal internet (not the tunnel) and tests real latency from your ISP.")
        self.info.setWordWrap(True); lay.addWidget(self.info)
        self.list = QListWidget(); lay.addWidget(self.list)
        row2 = QHBoxLayout()
        self.one_btn = QPushButton("Use selected IP for this profile"); self.one_btn.clicked.connect(self.use_one)
        self.many_btn = QPushButton(f"Spread best IPs over {n_cf_profiles} Cloudflare profile(s)" + (f" of group '{group}'" if group else ""))
        self.many_btn.clicked.connect(self.use_many); self.many_btn.setEnabled(n_cf_profiles > 0)
        row2.addWidget(self.one_btn); row2.addWidget(self.many_btn)
        lay.addLayout(row2)
        self.copy_btn = QPushButton("Copy all IPs"); self.copy_btn.clicked.connect(self.copy_all); lay.addWidget(self.copy_btn)
        self.n_cf = n_cf_profiles

    # -- scanning
    def start(self):
        self.list.clear(); self.bar.setValue(0)
        self.worker = ScanWorker(self.count.value(), self.port, self.sni, self, ipv6=self.v6.isChecked())
        self.worker.found.connect(self.on_found)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.info.setText("Scanning ...")
        self.worker.start()

    def stop(self):
        if self.worker: self.worker.stop()
        self.stop_btn.setEnabled(False)

    def on_found(self, ip, ms, colo):
        item = QListWidgetItem(f"{ms:>5} ms    {ip:<40}  {colo}")
        item.setData(Qt.UserRole, (ms, ip))
        pos = self.list.count()
        for i in range(self.list.count()):          # keep sorted: fastest first
            if self.list.item(i).data(Qt.UserRole)[0] > ms:
                pos = i; break
        self.list.insertItem(pos, item)
        if self.list.currentRow() < 0: self.list.setCurrentRow(0)

    def on_progress(self, done, total):
        self.bar.setMaximum(total); self.bar.setValue(done)

    def on_finished(self):
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        n = self.list.count()
        self.info.setText(f"Done: {n} working IP(s) found." if n else
                          "No working IP found. Check the SNI/port of the profile, or try again / more IPs.")

    # -- results
    def ips(self):
        return [self.list.item(i).data(Qt.UserRole)[1] for i in range(self.list.count())]

    def use_one(self):
        it = self.list.currentItem()
        if not it:
            QMessageBox.information(self, "Scanner", "Select an IP first."); return
        self.action = ("one", it.data(Qt.UserRole)[1]); self.accept()

    def use_many(self):
        ips = self.ips()[:10]
        if not ips:
            QMessageBox.information(self, "Scanner", "No IPs yet."); return
        self.action = ("many", ips); self.accept()

    def copy_all(self):
        QApplication.clipboard().setText("\n".join(self.ips()))

    def done(self, r):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.worker.wait(5000)
        super().done(r)
