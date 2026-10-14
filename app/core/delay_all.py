"""Real-delay test for many profiles at once (like 'Test all' in Hiddify / v2rayN).
Each profile gets its own temporary Xray process on a private port, so nothing
touches the active connection or the Windows system proxy."""
import os, socket, subprocess, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core.config_generator import write_config
from app.utils.latency import real_delay

BASE_PORT = 21000
TEST_URL = "http://www.gstatic.com/generate_204"      # tests point this at a local server
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _is_timeout(e):
    return isinstance(e, (TimeoutError, socket.timeout)) or "timed out" in str(e).lower()


def _wait_port(port, timeout=4.0, proc=None):
    """True when something listens on the port. If `proc` (the xray we just started) already exited, the port
    belongs to somebody else (or the config is invalid): return False at once instead of waiting / lying."""
    end = time.time() + timeout
    while time.time() < end:
        if proc is not None and proc.poll() is not None:
            return False
        with socket.socket() as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


def test_one(executable, profile, port, url=None, timeout=8, verify=None):
    """Returns delay in ms, or -1 if the profile does not work.
    verify(port) -> ms or None: extra check after the basic one (e.g. real YouTube/Instagram requests)."""
    url = url or TEST_URL
    tmp = Path(tempfile.mkdtemp(prefix="nbtest_"))
    cfg = tmp / "t.json"
    proc = None
    try:
        write_config(profile, cfg, {"routing": {"lan": False}},
                     socks_port=0, http_port=port, loglevel="none")
        proc = subprocess.Popen([str(executable), "run", "-c", str(cfg)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=NOWIN)
        if not _wait_port(port, proc=proc):
            return -1
        best, ok, tries = None, 0, 0
        while ok < 2 and tries < 4:             # first request warms up; a quick one-off error must not kill a good server
            tries += 1
            try:
                ms = real_delay(f"http://127.0.0.1:{port}", url, timeout)
                best = ms if best is None else min(best, ms)
                ok += 1
            except Exception as e:
                if _is_timeout(e):
                    break                       # really silent = dead; do not wait again
        if best is None:
            return -1
        if verify is not None:
            v = verify(port)
            return -1 if v is None else v
        return best
    except Exception:
        return -1
    finally:
        if proc:
            proc.terminate()
            try: proc.wait(timeout=2)
            except Exception: proc.kill()
        try:
            cfg.unlink(missing_ok=True); tmp.rmdir()
        except Exception:
            pass


def test_many(executable, items, on_result, workers=10, cancelled=lambda: False, url=None):
    """items: list of (key, profile). on_result(key, ms) is called as each finishes."""
    def job(n_item):
        n, (key, prof) = n_item
        if cancelled():
            return
        ms = test_one(executable, prof, BASE_PORT + n, url=url)
        on_result(key, ms)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(job, enumerate(items)))
