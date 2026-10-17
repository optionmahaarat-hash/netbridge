"""WARP (and, later, Psiphon / Tor) through the Aether core: https://github.com/CluvexStudio/Aether  (AGPL-3.0).

Aether is a separate program. NetBridge does NOT ship it: on first use it is downloaded from the project's own GitHub
releases to cores/aether/, its SHA-256 is checked, and it runs as its own process with a local SOCKS5 port. NetBridge's
Xray then uses that port as an ordinary "socks" outbound, so everything else (routing, system proxy, tests) is unchanged.

Everything here that can be tested without a network is a plain function.
"""
import hashlib
import io
import json
import os
import queue
import re
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = "CluvexStudio/Aether"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"       # only files of the official repo are accepted
CORE_DIR = Path("cores/aether")
EXE_NAME = "aether.exe"
DATA_DIR = Path("data/aether")                                          # identity (aether.toml) and last-gateway cache live here
DEFAULT_PORT = 1819
MAX_BYTES = 200 * 1024 * 1024
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AetherError(Exception):
    pass


# ------------------------------------------------------------------ choosing and checking the download
def pick_asset(release):
    """From the GitHub release JSON: (windows_zip_asset, checksum_asset_or_None). The exact file name is not assumed:
    the Windows x86-64 zip is recognised by its name. Raises AetherError."""
    assets = [a for a in (release.get("assets") or []) if isinstance(a, dict) and a.get("name")]
    best, best_score = None, -1
    for a in assets:
        n = a["name"].lower()
        if "windows" not in n and "win64" not in n and "win-" not in n:
            continue
        if not n.endswith(".zip"):
            continue
        if any(x in n for x in ("arm64", "aarch64", "i686", "i386", "win32")):
            continue
        score = 2 if any(x in n for x in ("x86_64", "amd64", "x64")) else 1
        if score > best_score:
            best, best_score = a, score
    if best is None:
        raise AetherError("no Windows download found in the latest Aether release")
    want = {best["name"].lower() + s for s in (".sha256", ".sha256sum", ".sha256.txt")}
    sums = next((a for a in assets if a["name"].lower() in want), None)
    if sums is None:
        sums = next((a for a in assets if a["name"].lower() in ("sha256sums", "sha256sums.txt", "checksums.txt")), None)
    return best, sums


def parse_sha(text, filename):
    """Hex digest for `filename` from a *.sha256 file ('<hash>' or '<hash>  name') or a SHA256SUMS list. None if absent."""
    fn = filename.lower()
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    for line in lines:
        parts = line.split()
        if not parts or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            continue
        if len(parts) == 1 and len(lines) == 1:
            return parts[0].lower()
        if len(parts) >= 2 and parts[-1].lstrip("*").split("/")[-1].lower() == fn:
            return parts[0].lower()
    if len(lines) == 1 and re.fullmatch(r"[0-9a-fA-F]{64}", lines[0].split()[0] if lines[0].split() else ""):
        return lines[0].split()[0].lower()
    return None


def extract_exe(zip_bytes):
    """The bytes of aether.exe from the zip (any folder inside). Nothing else is ever written to disk."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                if info.filename.replace("\\", "/").split("/")[-1].lower() == EXE_NAME:
                    if info.file_size > MAX_BYTES:
                        raise AetherError("aether.exe in the zip is too large")
                    return z.read(info)
    except zipfile.BadZipFile:
        raise AetherError("the download is not a valid zip file")
    raise AetherError("aether.exe was not found inside the download")


def extract_pt(zip_bytes, dest_dir):
    """Writes the pluggable transports (obfs4, snowflake, ...) that ship in the zip's pt/ folder to dest_dir/pt/ - Tor bridges need them.
    Only plain files directly or below a 'pt' folder, no path tricks, size-capped. Returns the number of files written."""
    n, total = 0, 0
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                parts = [x for x in info.filename.replace("\\", "/").split("/") if x]
                if "pt" not in parts[:-1] or any(x in ("..", ".") or ":" in x for x in parts):
                    continue
                rel = parts[parts.index("pt") + 1:]
                total += info.file_size
                if info.file_size > MAX_BYTES or total > MAX_BYTES:
                    raise AetherError("the pt/ folder in the zip is too large")
                target = Path(dest_dir, "pt", *rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info)); n += 1
    except zipfile.BadZipFile:
        raise AetherError("the download is not a valid zip file")
    return n


def _http(url, timeout=30, proxy=None, limit=MAX_BYTES):
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    req = urllib.request.Request(url, headers={"User-Agent": "NetBridge", "Accept": "application/octet-stream, application/json"})
    with urllib.request.build_opener(*handlers).open(req, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise AetherError("download is larger than expected")
    return data


def download_core(dest_dir=None, fetch=_http, proxy=None, progress=lambda s: None):
    """Downloads the latest Aether for Windows, verifies SHA-256 and installs aether.exe. Returns (path, tag).
    Refuses to install when no checksum is published or it does not match. `fetch(url, proxy=...)` is replaceable for tests."""
    dest_dir = Path(dest_dir or CORE_DIR)
    progress("Looking for the latest Aether release...")
    try:
        release = json.loads(fetch(API_LATEST, proxy=proxy).decode("utf-8"))
    except AetherError:
        raise
    except Exception as e:
        raise AetherError(f"could not read the release list: {e}")
    asset, sums = pick_asset(release)
    for a in (asset, sums):
        if a and not str(a.get("browser_download_url", "")).startswith(DOWNLOAD_PREFIX):
            raise AetherError("refusing a download address outside the official Aether releases")
    if sums is None:
        raise AetherError("the release has no SHA-256 file - refusing to install an unchecked program")
    progress(f"Downloading {asset['name']} ...")
    blob = fetch(asset["browser_download_url"], timeout=120, proxy=proxy)
    expected = parse_sha(fetch(sums["browser_download_url"], proxy=proxy).decode("utf-8", "replace"), asset["name"])
    if not expected:
        raise AetherError("could not read the SHA-256 value for the download")
    got = hashlib.sha256(blob).hexdigest()
    if got != expected:
        raise AetherError("SHA-256 does not match - the download is damaged or was changed. Nothing was installed.")
    exe = extract_exe(blob)
    dest_dir.mkdir(parents=True, exist_ok=True)
    extract_pt(blob, dest_dir)
    target = dest_dir / EXE_NAME
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(exe)
    os.replace(tmp, target)
    (dest_dir / "VERSION.txt").write_text(f"{release.get('tag_name', '?')}\nsha256 of the zip: {got}\n"
                                          f"source: https://github.com/{REPO}  (AGPL-3.0)\n", encoding="utf-8")
    return target, release.get("tag_name", "?")


def installed(dest_dir=None):
    return (Path(dest_dir or CORE_DIR) / EXE_NAME).exists()


# ------------------------------------------------------------------ running it
MODES = ("warp", "tor", "tor-only")            # warp = WARP only; tor = Tor carried inside the WARP tunnel; tor-only = plain Tor (bridges when blocked)


def build_args(exe, port=DEFAULT_PORT, mode="h3", config=None, protocol="masque", tor=None, tor_port=None, tor_dir=None, family="4"):
    """Command line. Every choice is given as a flag, because a flag suppresses that question (Aether asks interactively otherwise).
    family: which gateway addresses to scan: "4" (IPv4), "6" (IPv6) or "dual". Some networks only let IPv6 through.
    mode: "h3" = MASQUE over HTTP/3 (default), "h2" = MASQUE over HTTP/2 with ClientHello fragmentation (when UDP/QUIC is blocked).
    tor: None, "tor" (Tor inside the tunnel; its proxy is tor_port) or "tor-only" (no WARP; the proxy on `port` is Tor)."""
    if protocol not in ("masque", "wg", "gool"):
        raise ValueError("protocol must be masque, wg or gool")
    if mode not in ("h3", "h2"):
        raise ValueError("mode must be h3 or h2")
    if tor not in (None, "tor", "tor-only"):
        raise ValueError("tor must be None, 'tor' or 'tor-only'")
    if family not in ("4", "6", "dual"):
        raise ValueError("family must be 4, 6 or dual")
    if tor == "tor-only":
        args = [str(exe), "--bind", f"127.0.0.1:{int(port)}", "--tor-only"]
    else:
        args = [str(exe), "--bind", f"127.0.0.1:{int(port)}", {"4": "-4", "6": "-6", "dual": "--dual"}[family], f"--{protocol}", "--turbo", "--noize", "firewall", "--quick-reconnect"]
        if protocol == "masque" and mode == "h2":
            args += ["--h2", "--fragment"]
        if tor == "tor":
            args += ["--tor", "--tor-bind", f"127.0.0.1:{int(tor_port or port + 1)}"]
    if tor and tor_dir:
        args += ["--tor-dir", str(tor_dir)]
    if config:
        args += ["--config", str(config)]
    return args


def socks_ready(port, timeout=1.0):
    """True when a SOCKS5 server answers the greeting on 127.0.0.1:port (it listens AND speaks SOCKS)."""
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(b"\x05\x01\x00")
            return s.recv(2) == b"\x05\x00"
    except OSError:
        return False


def free_port(start=DEFAULT_PORT, tries=20):
    for p in range(start, start + tries):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise AetherError("no free local port for Aether")


class AetherManager:
    def __init__(self, executable=None, data_dir=None):
        self.executable = Path(executable or (CORE_DIR / EXE_NAME))
        self.data_dir = Path(data_dir or DATA_DIR)
        self.process = None
        self.port = None
        self.kind = None                      # "warp" / "tor" / "tor-only": what is running
        self._lines = []
        self._lock = threading.Lock()

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def tail(self, n=12):
        with self._lock:
            return list(self._lines[-n:])

    def _pump(self, proc):
        for line in proc.stdout:
            with self._lock:
                self._lines.append(line.rstrip())
                del self._lines[:-200]

    def _launch(self, port, mode, tor=None, tor_port=None, protocol="masque", family="4"):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        args = build_args(self.executable, port, mode, config=self.data_dir / "aether.toml", tor=tor, tor_port=tor_port,
                          tor_dir=self.data_dir / "tor", protocol=protocol, family=family)
        self.process = subprocess.Popen(args, cwd=str(self.data_dir), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
        threading.Thread(target=self._pump, args=(self.process,), daemon=True).start()

    def start(self, wait=45, cancelled=lambda: False, progress=lambda s: None, ready=socks_ready, sleep=time.sleep,
              modes=("h3", "h2"), kind="warp", protocol="masque", family="4"):
        """Starts Aether and waits until the SOCKS5 port NetBridge will use works. kind: "warp", "tor" or "tor-only".
        WARP/Tor-in-tunnel try HTTP/3 first, then HTTP/2+fragment. Returns that port. Raises AetherError with the last log lines."""
        if kind not in MODES:
            raise ValueError("kind must be one of " + ", ".join(MODES))
        if not self.executable.exists():
            raise AetherError("Aether is not installed yet")
        self.stop()
        port = free_port()
        tor_port = free_port(port + 1) if kind == "tor" else None
        use = port if kind != "tor" else tor_port
        if kind != "warp":
            wait = max(wait, 240)                                   # Tor downloads its directory first; bridges can take longer still
        for mode in (modes if kind != "tor-only" and (protocol == "masque" or kind == "tor") else ("h3",)):
            what = {"warp": (f"MASQUE {'HTTP/3' if mode == 'h3' else 'HTTP/2 + fragment'}" if protocol == "masque"
                             else {"wg": "WireGuard", "gool": "WARP-in-WARP (gool)"}.get(protocol, protocol)) + f", IPv{family}", "tor": f"Tor inside MASQUE {mode.upper()}",
                    "tor-only": "Tor alone"}[kind]
            progress(f"Starting Aether ({what}) on port {use} - the first start can take a few minutes ...")
            self._launch(port, mode, tor=None if kind == "warp" else kind, tor_port=tor_port, protocol=protocol, family=family)
            end = time.time() + wait
            while time.time() < end:
                if cancelled():
                    self.stop(); raise AetherError("cancelled")
                if self.process.poll() is not None:
                    break
                if ready(use):
                    self.port, self.kind = use, kind
                    return use
                sleep(0.5)
            progress("Aether did not become ready" + (" - trying the next mode" if mode != modes[-1] and kind != "tor-only" else ""))
            self.stop()
        tail = "\n".join(self.tail())
        if kind != "warp" and re.search(r"unexpected argument|unknown (option|argument)|not (built|compiled)|unrecognized", tail, re.I):
            raise AetherError("this Aether build has no Tor support (it must be built with the 'tor' feature). Last output:\n" + tail)
        raise AetherError("Aether did not start. Last output:\n" + tail)

    def stop(self):
        proc, self.process = self.process, None
        self.port = None
        self.kind = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        if proc is not None and proc.stdout is not None:
            try:
                proc.stdout.close()
            except Exception:
                pass


# ------------------------------------------------------------------ the profile NetBridge uses to reach it
def warp_profile(port=DEFAULT_PORT):
    """A normal 'socks' profile pointing at the local Aether port, marked engine=aether."""
    return {"type": "socks", "name": "WARP (Aether)", "server": "127.0.0.1", "port": int(port), "group": "WARP",
            "engine": "aether", "aether_kind": "warp", "security": "", "network": "tcp"}


def tor_profile(port=DEFAULT_PORT, kind="tor"):
    """A 'socks' profile pointing at Aether's Tor port. aether_kind tells which Aether mode must be running for it."""
    return {"type": "socks", "name": "Tor (Aether)" if kind == "tor" else "Tor alone (Aether)", "server": "127.0.0.1", "port": int(port),
            "group": "Tor", "engine": "aether", "aether_kind": kind, "security": "", "network": "tcp"}


def needs_kind(profile):
    return profile.get("aether_kind", "warp") if is_aether(profile) else None


def is_aether(profile):
    return isinstance(profile, dict) and profile.get("engine") == "aether"
