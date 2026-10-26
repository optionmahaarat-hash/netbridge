from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QHeaderView, QPlainTextEdit)
from app.core import resolverscan, autobypass


class ScanWorker(QThread):
    row = Signal(dict)
    done = Signal(list)

    def __init__(self, resolvers, parent=None):
        super().__init__(parent)
        self.resolvers, self._stop = resolvers, False

    def stop(self):
        self._stop = True

    def run(self):
        rows = resolverscan.scan(self.resolvers, cancelled=lambda: self._stop, on_row=self.row.emit)
        self.done.emit(rows)


class ResolverDialog(QDialog):
    """Finds which DNS resolvers answer on this network (UDP / TCP / DoT / DoH) and lets AUTO use the working DoH ones."""
    def __init__(self, settings, save, parent=None):
        super().__init__(parent)
        self.settings, self.save, self.worker, self.rows = settings, save, None, []
        self.setWindowTitle("DNS resolver finder / \u06cc\u0627\u0628\u0646\u062f\u0647 \u0631\u0632\u0648\u0644\u0648\u0631")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Tests each resolver over UDP, TCP, DoT and DoH from this network (ms; - = blocked). "
                             "Working DoH servers can be handed to AUTO for the ECH key lookup."))
        self.extra = QPlainTextEdit(); self.extra.setMaximumHeight(60)
        self.extra.setPlaceholderText("Optional: your own resolvers, one per line:  label,ip[,https://doh-url]")
        lay.addWidget(self.extra)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Resolver", "IP", "UDP", "TCP", "DoT", "DoH"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.table, 1)
        self.status = QLabel(""); lay.addWidget(self.status)
        r = QHBoxLayout()
        self.go = QPushButton("Scan"); self.go.setObjectName("primary"); self.go.clicked.connect(self.start); r.addWidget(self.go)
        self.use = QPushButton("Use working DoH in AUTO"); self.use.setEnabled(False); self.use.clicked.connect(self.apply); r.addWidget(self.use)
        self.clear = QPushButton("Clear saved"); self.clear.clicked.connect(self.clear_saved); r.addWidget(self.clear)
        r.addStretch(1)
        close = QPushButton("Close"); close.clicked.connect(self.close); r.addWidget(close)
        lay.addLayout(r)
        n = len(self.settings.get("doh_extra") or [])
        self.status.setText(f"{n} saved DoH server(s) in use by AUTO." if n else "")

    def _custom(self):
        out = []
        for line in self.extra.toPlainText().splitlines():
            p = [x.strip() for x in line.split(",")]
            if len(p) >= 2 and p[1]:
                doh = p[2] if len(p) > 2 and p[2].startswith("https://") else None
                out.append((p[0] or p[1], p[1], doh, None))
        return out

    def start(self):
        self.table.setRowCount(0); self.rows = []; self.use.setEnabled(False)
        self.go.setEnabled(False); self.status.setText("Scanning ...")
        self.worker = ScanWorker(resolverscan.RESOLVERS + self._custom(), self)
        self.worker.row.connect(self.add_row); self.worker.done.connect(self.finished)
        self.worker.start()

    @staticmethod
    def _ms(v):
        return "-" if v is None or v < 0 else str(v)

    def add_row(self, r):
        i = self.table.rowCount(); self.table.insertRow(i)
        for c, v in enumerate((r["label"], r["ip"], self._ms(r.get("udp")), self._ms(r.get("tcp")), self._ms(r.get("dot")), self._ms(r.get("doh")))):
            it = QTableWidgetItem(v)
            if c >= 2 and v != "-":
                it.setForeground(Qt.darkGreen)
            self.table.setItem(i, c, it)

    def finished(self, rows):
        self.rows = rows; self.go.setEnabled(True)
        doh = resolverscan.working_doh(rows)
        ok = sum(1 for r in rows if resolverscan.best_ms(r) is not None)
        self.status.setText(f"{ok} of {len(rows)} resolvers answer; {len(doh)} DoH server(s) work.")
        self.use.setEnabled(bool(doh))

    def apply(self):
        doh = resolverscan.working_doh(self.rows)[:6]
        self.settings["doh_extra"] = doh
        autobypass.EXTRA_DOH[:] = doh
        self.save(self.settings)
        self.status.setText(f"AUTO will try these DoH servers first: {len(doh)}")

    def clear_saved(self):
        self.settings["doh_extra"] = []
        autobypass.EXTRA_DOH[:] = []
        self.save(self.settings)
        self.status.setText("Saved list cleared.")

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.worker.wait(3000)
        super().closeEvent(e)
