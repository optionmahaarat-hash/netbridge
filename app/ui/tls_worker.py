import threading
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QThread, Signal
from app.core import tlsup, exitscan

PORT0 = 23000


class TlsWorker(QThread):
    """Tries to find a working TLS door for each plain profile (see app/core/tlsup.py)."""
    result = Signal(object, object, str)      # original profile, new profile or None, text
    progress = Signal(int, int)

    def __init__(self, exe, profiles, parent=None):
        super().__init__(parent)
        self.exe, self.profiles, self._stop, self._n, self._lock = exe, profiles, False, 0, threading.Lock()

    def stop(self): self._stop = True

    def _port(self):
        with self._lock:
            self._n += 1
            return PORT0 + self._n

    def run(self):
        done = [0]
        def works(q):
            if self._stop: return None
            return exitscan.probe_exit(self.exe, q, self._port())
        def job(p):
            if self._stop: return
            try:
                q, info = tlsup.find_tls(p, works)
                text = exitscan.describe(info) if q else info
            except Exception as e:
                q, text = None, f"{type(e).__name__}: {e}"[:140]
            self.result.emit(p, q, text)
            done[0] += 1; self.progress.emit(done[0], len(self.profiles))
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(job, self.profiles))
