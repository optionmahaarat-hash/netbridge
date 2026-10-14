"""Self-update with a signed manifest.

latest.json  = {"app","version","url","sha256","size","notes":{"fa","en"},"signature"}
signature    = Ed25519 over  "app|version|sha256|size|url"   (private key stays with the developer; the public key is in assets/update_pubkey.txt)
A manifest or zip that is not signed with that key is NEVER installed - so a hacked download server cannot push code to the family's PCs.
"""
import base64, hashlib, json, re, subprocess, sys, urllib.request, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin

from app.lite import paths
from app.lite.version import APP_ID

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class UpdateError(Exception):
    pass


def parse_version(v):
    parts = re.findall(r"\d+", str(v).split("-")[0])
    return tuple(int(x) for x in parts) or (0,)


def is_newer(new, cur):
    return parse_version(new) > parse_version(cur)


def signed_message(m):
    return f"{m['app']}|{m['version']}|{m['sha256']}|{m['size']}|{m['url']}".encode()


def load_public_key(path=None):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    p = Path(path) if path else ASSETS / "update_pubkey.txt"
    if not p.exists():
        raise UpdateError("update key is missing (assets/update_pubkey.txt) - build the release first")
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(p.read_text().strip()))


def verify_manifest(m, public_key):
    from cryptography.exceptions import InvalidSignature
    try:
        for k in ("app", "version", "sha256", "size", "url", "signature"):
            if k not in m: raise UpdateError(f"manifest field missing: {k}")
        if m["app"] != APP_ID: raise UpdateError("manifest is for another app")
        public_key.verify(base64.b64decode(m["signature"]), signed_message(m))
    except InvalidSignature:
        raise UpdateError("signature is not valid - update refused")
    except UpdateError:
        raise
    except Exception as e:                                  # bad base64, wrong types ...
        raise UpdateError(f"manifest is damaged: {type(e).__name__}")
    return m


def _opener(proxy):
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    return urllib.request.build_opener(*handlers)


def fetch_manifest(urls, proxy=None, timeout=20):
    """Tries every URL (through the tunnel first, then directly). Returns (manifest, manifest_url)."""
    errors = []
    for px in ([proxy, None] if proxy else [None]):
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "NetBridgeLite"})
                return json.loads(_opener(px).open(req, timeout=timeout).read().decode("utf-8")), u
            except Exception as e:
                errors.append(f"{u}: {e}")
    raise UpdateError("; ".join(errors[:2]) or "no update address")


def check(current, urls, public_key, proxy=None):
    """Returns the verified manifest (with '_base') if a newer version exists, else None."""
    if not urls:
        raise UpdateError("no update address")
    m, mu = fetch_manifest(urls, proxy)
    verify_manifest(m, public_key)                      # verify BEFORE trusting anything inside
    if not is_newer(m["version"], current):
        return None
    m["_base"] = mu
    return m


def download(m, dest_dir, proxy=None, progress=None, timeout=60):
    """Downloads the zip, checks size + SHA256. Returns the file path."""
    dest_dir = Path(dest_dir); dest_dir.mkdir(parents=True, exist_ok=True)
    url = urljoin(m["_base"], m["url"])
    out = dest_dir / f"{APP_ID}-{m['version']}.zip"
    h, got, total = hashlib.sha256(), 0, int(m["size"])
    req = urllib.request.Request(url, headers={"User-Agent": "NetBridgeLite"})
    with _opener(proxy).open(req, timeout=timeout) as r, open(out, "wb") as f:
        while True:
            chunk = r.read(256 * 1024)
            if not chunk: break
            f.write(chunk); h.update(chunk); got += len(chunk)
            if got > total + 1024: break                 # more than announced
            if progress: progress(min(100, int(got * 100 / max(total, 1))))
    if got != total or h.hexdigest() != m["sha256"].lower():
        out.unlink(missing_ok=True)
        raise UpdateError("downloaded file is damaged or was changed (hash mismatch)")
    return out


def stage(zip_path, staging_dir, exe_name):
    """Extracts safely (no path tricks) and checks that the new build contains the program."""
    staging_dir = Path(staging_dir)
    if staging_dir.exists():
        import shutil; shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)
    root = staging_dir.resolve()
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        for n in names:
            p = PurePosixPath(n.replace("\\", "/"))
            if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]):
                raise UpdateError(f"unsafe path in update: {n}")
        if exe_name not in {PurePosixPath(n).as_posix() for n in names}:
            raise UpdateError(f"{exe_name} is not inside the update")
        z.extractall(root)
    return root


def apply_script(app_dir, staging, exe_name, zip_path):
    """Windows batch: wait until the app exits, copy the new files over it (data\\ is kept), start it again."""
    app_dir, staging = str(app_dir), str(staging)
    upd = str(Path(app_dir) / "updates")
    return "\r\n".join([
        "@echo off",
        f'set "APP={app_dir}"',
        f'set "STAGE={staging}"',
        f'set "EXE={exe_name}"',
        f'set "UPD={upd}"',
        "set /a n=0",
        ":wait",
        'tasklist /FI "IMAGENAME eq %EXE%" 2>nul | find /I "%EXE%" >nul',
        "if errorlevel 1 goto copy",
        "set /a n+=1",
        "if %n% GEQ 40 goto fail",
        "timeout /t 1 /nobreak >nul",
        "goto wait",
        ":copy",
        'robocopy "%STAGE%" "%APP%" /E /R:8 /W:1 /XD data updates /NFL /NDL /NJH /NJS /NP >nul',
        "if %errorlevel% GEQ 8 goto fail",
        'rmdir /S /Q "%STAGE%" >nul 2>&1',
        f'del /Q "{zip_path}" >nul 2>&1',
        'start "" "%APP%\\%EXE%"',
        "exit /b 0",
        ":fail",
        'echo failed> "%UPD%\\update_failed.txt"',
        'start "" "%APP%\\%EXE%"',
        "exit /b 1",
        "",
    ])


def apply_supported():
    return sys.platform == "win32" and paths.frozen()


def launch_apply(app_dir, staging, exe_name, zip_path):
    """Writes + starts apply_update.bat detached. The caller must quit the app right after."""
    upd = Path(app_dir) / "updates"; upd.mkdir(exist_ok=True)
    bat = upd / "apply_update.bat"
    bat.write_text(apply_script(app_dir, staging, exe_name, zip_path), encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=NOWIN | getattr(subprocess, "DETACHED_PROCESS", 0),
                     close_fds=True)
    return bat


def take_failure_flag(app_dir):
    f = Path(app_dir) / "updates" / "update_failed.txt"
    if f.exists():
        f.unlink(missing_ok=True); return True
    return False
