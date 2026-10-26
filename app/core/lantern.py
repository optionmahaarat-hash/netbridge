"""Opens an already-installed Lantern (https://github.com/getlantern/lantern, GPL-3.0).

NetBridge does NOT contain, download or modify Lantern: its licence (GPL-3.0) does not allow building it into this program. This
module only looks for the program the user installed themselves and starts it, like double-clicking its icon.
"""
import os
import subprocess
from pathlib import Path

PAGE = "https://github.com/getlantern/lantern"
NAMES = ("lantern.exe", "Lantern.exe")
SUBDIRS = ("Lantern", "lantern", "Programs/Lantern", "Programs/lantern")


def candidates(env=None):
    """Folders where Lantern's Windows installer usually puts it, most likely first."""
    env = os.environ if env is None else env
    roots = [env.get(k) for k in ("LOCALAPPDATA", "APPDATA", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    out = []
    for r in roots:
        if r:
            out += [Path(r) / sub for sub in SUBDIRS]
    return out


def find(env=None, exists=lambda p: p.is_file()):
    """Path of the installed Lantern program, or None."""
    for d in candidates(env):
        for n in NAMES:
            p = d / n
            if exists(p):
                return p
    return None


def launch(path, popen=subprocess.Popen):
    """Starts Lantern as its own program (detached: closing NetBridge does not close it)."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    popen([str(path)], cwd=str(Path(path).parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL, creationflags=flags)


# Old, unverified reports say Lantern listens as an HTTP proxy on 127.0.0.1:8787. We never rely on it: this only TESTS a port.
GUESS_PORT = 8787
TEST_URL = "http://connectivitycheck.gstatic.com/generate_204"


def probe_proxy(port=GUESS_PORT, host="127.0.0.1", timeout=4.0, opener=None):
    """Tests whether an HTTP proxy answers on host:port (ms) - and whether it really carries a request out (True/False).
    Returns {"listening": bool, "works": bool, "ms": int|None, "error": str}. Never raises."""
    import socket
    import time
    import urllib.request
    out = {"listening": False, "works": False, "ms": None, "error": ""}
    try:
        socket.create_connection((host, int(port)), timeout=min(timeout, 2.0)).close()
        out["listening"] = True
    except OSError as e:
        out["error"] = f"nothing listens on {host}:{port} ({e.__class__.__name__})"
        return out
    try:
        op = opener or urllib.request.build_opener(urllib.request.ProxyHandler({"http": f"http://{host}:{int(port)}"}))
        t = time.time()
        with op.open(urllib.request.Request(TEST_URL, headers={"User-Agent": "NetBridge"}), timeout=timeout) as r:
            out["works"] = r.status in (200, 204)
        out["ms"] = int((time.time() - t) * 1000)
    except Exception as e:
        out["error"] = f"a port is open but the request failed: {e}"
    return out
