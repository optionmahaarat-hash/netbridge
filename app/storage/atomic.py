"""Crash-safe JSON/text writes: write to a temp file next to the target, then replace it in one step.
A power cut or a crash in the middle of a normal write_text() leaves a half-written (corrupt) file, which
used to wipe the whole server list / settings on the next start."""
import json
import os
import tempfile
from pathlib import Path


def write_text_atomic(path, text, encoding="utf-8"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json_atomic(path, data):
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_json(path, default):
    """Parsed JSON, or `default` if the file is missing/corrupt. A corrupt file is kept as <name>.bad
    (so the user can recover it) instead of being silently overwritten by the next save."""
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception:
        try:
            os.replace(path, path.with_name(path.name + ".bad"))
        except OSError:
            pass
        return default
