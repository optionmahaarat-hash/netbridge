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
