from pathlib import Path
import subprocess, threading, queue

class XrayManager:
    def __init__(self, executable="cores/xray/xray.exe"):
        self.executable = Path(executable)
        self.process = None
        self._q = queue.Queue()

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self, config_path):
        if not self.executable.exists():
            raise FileNotFoundError(f"Xray executable not found: {self.executable}")
        if self.running:
            self.stop()
        self.process = subprocess.Popen(
            [str(self.executable), "run", "-c", str(config_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        q = queue.Queue()
        self._q = q
        threading.Thread(target=self._pump, args=(self.process, q), daemon=True).start()

    def _pump(self, proc, q):
        for line in proc.stdout:
            q.put(line.rstrip())
        q.put("[xray exited]")

    def check_config(self, config_path):
        """Run `xray run -test`. Returns (ok, message)."""
        if not self.executable.exists():
            return False, f"Xray executable not found: {self.executable}"
        try:
            r = subprocess.run(
                [str(self.executable), "run", "-test", "-c", str(config_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=20)
        except subprocess.TimeoutExpired:
            return False, "Xray did not finish the config check in 20 seconds."
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out.splitlines()[-1] if out else ""

    def version(self):
        """Returns e.g. (26, 7, 28) or None."""
        import re
        if not self.executable.exists(): return None
        try:
            r = subprocess.run([str(self.executable), "version"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            m = re.search(r"Xray (\d+)\.(\d+)\.(\d+)", r.stdout)
            return tuple(int(x) for x in m.groups()) if m else None
        except Exception:
            return None

    def stop(self):
        proc, self.process = self.process, None
        if proc and proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired: pass
        if proc is not None and proc.stdout is not None:
            try: proc.stdout.close()
            except Exception: pass

    def read_all_available(self):
        lines = []
        while len(lines) < 50:
            try: lines.append(self._q.get_nowait())
            except queue.Empty: break
        return lines
