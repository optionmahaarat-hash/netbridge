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
import shutil
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
MODES = ("warp", "tor", "tor-only", "psiphon", "psiphon-only")      # warp = WARP only; tor / psiphon = carried inside the WARP tunnel; *-only = no WARP
SIDE_KINDS = ("tor", "psiphon")                                      # these have a second proxy port: that one is NetBridge's
ONLY_KINDS = ("tor-only", "psiphon-only")                            # these have no tunnel at all: the --bind port is the proxy
REGION_RE = re.compile(r"^[A-Za-z]{2}$")


BRIDGE_TRANSPORTS = ("obfs4", "snowflake", "meek", "meek_lite", "webtunnel", "scramblesuit", "conjure")
_IPPORT = r"(?:\[[0-9a-fA-F:]+\]|[0-9.]+):\d{1,5}"


def parse_bridges(text):
    """Cleans pasted Tor bridge lines (from bridges.torproject.org, the email bot or Telegram bot): drops blanks, '#' comments and a
    leading 'Bridge '. A line must start with a known transport (obfs4, snowflake, webtunnel ...) or be a plain 'IP:port [FINGERPRINT]'.
    Returns (good_lines, bad_lines); duplicates are removed."""
    good, bad = [], []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("bridge "):
            line = line[7:].strip()
        head = line.split(None, 1)[0].lower()
        ok = (head in BRIDGE_TRANSPORTS and len(line.split()) >= 2) or re.match(r"^" + _IPPORT + r"(\s+[0-9A-Fa-f]{40})?$", line)
        if ok:
            if line not in good:
                good.append(line)
        else:
            bad.append(raw.strip())
    return good, bad


def build_args(exe, port=DEFAULT_PORT, mode="h3", config=None, protocol="masque", tor=None, tor_port=None, tor_dir=None, family="4",
               psiphon=None, psiphon_port=None, psiphon_dir=None, region=None, bridge_file=None, bridges_now=False, upstream=None,
               psiphon_mode=None, noize="firewall", enroll_address=None):
    """Command line. Every choice is given as a flag, because a flag suppresses that question (Aether asks interactively otherwise).
    family: which gateway addresses to scan: "4" (IPv4), "6" (IPv6) or "dual". Some networks only let IPv6 through.
    mode: "h3" = MASQUE over HTTP/3 (default), "h2" = MASQUE over HTTP/2 with ClientHello fragmentation (when UDP/QUIC is blocked).
    tor: None, "tor" (Tor inside the tunnel; its proxy is tor_port) or "tor-only" (no WARP; the proxy on `port` is Tor).
    psiphon: None, "psiphon" (inside the tunnel; proxy psiphon_port) or "psiphon-only". region: two-letter exit country for Psiphon.
    (Psiphon itself is a built-in part of Aether's release: its binary is in the pt/ folder next to aether.exe.)"""
    if protocol not in ("masque", "wg", "gool", "wom"):
        raise ValueError("protocol must be masque, wg, gool or wom (WireGuard over MASQUE)")
    if mode not in ("h3", "h2"):
        raise ValueError("mode must be h3 or h2")
    if tor not in (None, "tor", "tor-only"):
        raise ValueError("tor must be None, 'tor' or 'tor-only'")
    if family not in ("4", "6", "dual"):
        raise ValueError("family must be 4, 6 or dual")
    if psiphon not in (None, "psiphon", "psiphon-only"):
        raise ValueError("psiphon must be None, 'psiphon' or 'psiphon-only'")
    if region and not REGION_RE.match(region):
        raise ValueError("region must be a two-letter country code")
    if tor and psiphon:
        raise ValueError("choose Tor or Psiphon, not both")
    if psiphon_mode not in (None, "cdn", "direct"):
        raise ValueError("psiphon_mode must be None, 'cdn' (fronted meek only) or 'direct' (fronting off)")
    if noize not in ("firewall", "gfw"):
        raise ValueError("noize must be 'firewall' (balanced) or 'gfw' (heavier, for severe filtering)")
    if tor == "tor-only":
        args = [str(exe), "--bind", f"127.0.0.1:{int(port)}", "--tor-only"]
    elif psiphon == "psiphon-only":
        args = [str(exe), "--bind", f"127.0.0.1:{int(port)}", "--psiphon-only"]
    else:
        args = [str(exe), "--bind", f"127.0.0.1:{int(port)}", {"4": "-4", "6": "-6", "dual": "--dual"}[family], ("--wg-over-masque" if protocol == "wom" else f"--{protocol}"), "--turbo", "--noize", noize, "--quick-reconnect"]
        if protocol in ("masque", "wom") and mode == "h2":
            args += ["--h2", "--fragment"]
        if tor == "tor":
            args += ["--tor", "--tor-bind", f"127.0.0.1:{int(tor_port or port + 1)}"]
        if psiphon == "psiphon":
            args += ["--psiphon", "--psiphon-bind", f"127.0.0.1:{int(psiphon_port or port + 1)}"]
    if tor and tor_dir:
        args += ["--tor-dir", str(tor_dir)]
    if tor and bridge_file:
        args += ["--tor-bridge-file", str(bridge_file)]
    if tor and bridges_now:
        args += ["--tor-bridges"]
    if psiphon:
        if psiphon_dir:
            args += ["--psiphon-dir", str(psiphon_dir)]
        if region:
            args += ["--psiphon-region", region.upper()]
        if psiphon_mode:
            args += ["--psiphon-mode", psiphon_mode]
    if enroll_address:
        if not re.match(r"^[\w.\-\[\]:]+$", enroll_address):
            raise ValueError("enroll_address must be a host name or IP, optionally with :port")
        args += ["--enroll-address", enroll_address]
    if upstream:
        if not re.match(r"^(socks5|http)://[\w.\-\[\]:%@]+:\d{1,5}$", upstream):
            raise ValueError("upstream must look like socks5://127.0.0.1:1080")
        args += ["--upstream", upstream]
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


def socks_tunnel_ok(port, host="www.google.com", dport=443, timeout=8.0):
    """True when a SOCKS5 CONNECT through 127.0.0.1:port really reaches `host`. Tor and Psiphon open their local SOCKS port
    long before their tunnel is up, so 'it answers the greeting' is not enough: this proves traffic goes out."""
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(b"\x05\x01\x00")
            if s.recv(2) != b"\x05\x00":
                return False
            name = host.encode()
            s.sendall(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + dport.to_bytes(2, "big"))
            rep = s.recv(4)
            return len(rep) >= 2 and rep[1] == 0
    except OSError:
        return False


def free_port(start=DEFAULT_PORT, tries=20):
    for p in range(start, start + tries):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise AetherError("no free local port for Aether")


FLAG_RE = re.compile(r"(?<![\w-])--[a-z0-9][a-z0-9-]*")


def supported_flags(exe, run=subprocess.run):
    """Flags the installed Aether prints in its --help (empty set when it cannot be asked). Newer options are only passed when listed,
    so an older core never gets an argument it would refuse."""
    try:
        r = run([str(exe), "--help"], capture_output=True, text=True, timeout=8, creationflags=NOWIN, stdin=subprocess.DEVNULL)
        return set(FLAG_RE.findall((r.stdout or "") + "\n" + (r.stderr or "")))
    except Exception:
        return set()


# ------------------------------------------------------------------ the WARP identity (aether.toml)
# Aether registers once and keeps the keys in aether.toml. A new registration can be refused (429) for a long time, and through a
# proxy chain it cannot be made at all (WhiteAesther's field notes), so the file is worth keeping safe. It holds PRIVATE keys.
IDENTITY_RE = re.compile(r"^aether[\w-]*\.toml$")          # aether.toml, aether-masque.toml (the log of a real run names this one), aether-wg.toml ...


def identity_files(data_dir=None):
    """The identity files Aether keeps in its data folder (one per transport), without backups."""
    d = Path(data_dir or DATA_DIR)
    try:
        return sorted(p for p in d.iterdir() if p.is_file() and IDENTITY_RE.match(p.name) and p.stat().st_size > 20)
    except OSError:
        return []


def identity_exists(data_dir=None):
    return bool(identity_files(data_dir))


def backup_identity(dest, data_dir=None):
    """Writes every identity file into one .zip. Raises AetherError when there is no identity yet."""
    files = identity_files(data_dir)
    if not files:
        raise AetherError("there is no Aether identity yet - connect WARP once first")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name)
    return Path(dest)


def restore_identity(src, data_dir=None):
    """Puts a backup (.zip made by backup_identity, or one .toml file) back; files it replaces are kept as *.bak.
    Only small files whose names look like Aether identity files are accepted."""
    src = Path(src)
    d = Path(data_dir or DATA_DIR)
    if not src.is_file():
        raise AetherError("that file does not exist")
    items = []
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            for i in z.infolist():
                if IDENTITY_RE.match(i.filename) and 0 < i.file_size <= 64 * 1024:
                    items.append((i.filename, z.read(i)))
    elif src.stat().st_size <= 64 * 1024:
        items.append((src.name if IDENTITY_RE.match(src.name) else "aether.toml", src.read_bytes()))
    items = [(n, c) for n, c in items if b"\x00" not in c and b"=" in c]
    if not items:
        raise AetherError("that does not look like an Aether identity backup")
    d.mkdir(parents=True, exist_ok=True)
    for name, content in items:
        dst = d / name
        if dst.exists():
            shutil.copyfile(dst, str(dst) + ".bak")
        dst.write_bytes(content)
    return [n for n, _ in items]


class AetherManager:
    def __init__(self, executable=None, data_dir=None):
        self.executable = Path(executable or (CORE_DIR / EXE_NAME))
        self.data_dir = Path(data_dir or DATA_DIR)
        self.process = None
        self.port = None
        self.kind = None                      # one of MODES: what is running
        self.bridges = []                     # the user's own Tor bridge lines (see parse_bridges); empty = Aether fetches its own
        self.upstream = None                  # socks5://127.0.0.1:port of a connection that already works: Aether dials through it
        self.bridges_now = False              # go to bridges at once instead of trying plain Tor first
        self.psiphon_mode = None              # None = Psiphon decides, "cdn" = fronted meek only, "direct" = fronting off (Aether >= 2.2)
        self.enroll_address = None            # WARP registration address (host or IP[:port]); only passed if this Aether lists --enroll-address
        self.last_notice = ""
        self.noize = "firewall"               # "gfw" = the heavier obfuscation profile for severe filtering (Aether >= 2.2)
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

    def _enroll_if_supported(self):
        if not self.enroll_address:
            return None
        if "--enroll-address" in supported_flags(self.executable):
            return self.enroll_address
        self.last_notice = "this Aether build does not list --enroll-address; the registration address was ignored"
        return None

    def _launch(self, port, mode, tor=None, tor_port=None, protocol="masque", family="4", psiphon=None, psiphon_port=None, region=None):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        bridge_file = None
        if tor and self.bridges:
            bridge_file = self.data_dir / "tor_bridges.txt"
            bridge_file.write_text("\n".join(self.bridges) + "\n", encoding="utf-8")
        args = build_args(self.executable, port, mode, config=self.data_dir / "aether.toml", tor=tor, tor_port=tor_port,
                          tor_dir=self.data_dir / "tor", protocol=protocol, family=family,
                          psiphon=psiphon, psiphon_port=psiphon_port, psiphon_dir=self.data_dir / "psiphon", region=region,
                          bridge_file=bridge_file, bridges_now=bool(self.bridges_now and tor), upstream=self.upstream,
                          psiphon_mode=self.psiphon_mode, noize=self.noize,
                          enroll_address=self._enroll_if_supported())
        env = None
        if getattr(self, "proxy_env", None):                     # registration (api.cloudflareclient.com) is filtered on some networks:
            env = dict(os.environ)                               # hand the running NetBridge proxy to Aether in case it honours these
            for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
                env[k] = self.proxy_env
        self.process = subprocess.Popen(args, cwd=str(self.data_dir), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, env=env,
                                        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
        threading.Thread(target=self._pump, args=(self.process,), daemon=True).start()

    def start(self, wait=45, cancelled=lambda: False, progress=lambda s: None, ready=socks_ready, sleep=time.sleep,
              modes=("h2", "h3"), kind="warp", protocol="masque", family="4", region=None):
        """Starts Aether and waits until the SOCKS5 port NetBridge will use works. kind: one of MODES.
        WARP/Tor-in-tunnel try HTTP/2+fragment first (WhiteAesther's field notes: it is the likelier winner on Iranian carriers, where UDP/QUIC is
        often cut), then HTTP/3. Returns that port. Raises AetherError with the last log lines."""
        if kind not in MODES:
            raise ValueError("kind must be one of " + ", ".join(MODES))
        if not self.executable.exists():
            raise AetherError("Aether is not installed yet")
        self.stop()
        self.last_notice = ""
        if protocol == "wom" and "--wg-over-masque" not in supported_flags(self.executable):
            raise AetherError("this Aether build does not list --wg-over-masque (WireGuard over MASQUE). Download the Aether core again (2.3 or newer).")
        if self.upstream and kind in ("warp", "tor", "psiphon") and not identity_exists(self.data_dir):
            progress("Heads-up: Aether has no saved identity yet, and a first registration cannot go through a proxy chain. If this fails, "
                     "untick 'connect via the current connection' for the FIRST start, then tick it again.")
        port = free_port()
        side_port = free_port(port + 1) if kind in SIDE_KINDS else None
        use = side_port if kind in SIDE_KINDS else port
        if kind != "warp":
            wait = max(wait, 420 if kind in ONLY_KINDS else 240)                                   # Tor downloads its directory first; bridges can take longer still
        for mode in (modes if kind not in ONLY_KINDS and (protocol in ("masque", "wom") or kind in SIDE_KINDS) else ("h3",)):
            what = {"warp": (f"MASQUE {'HTTP/3' if mode == 'h3' else 'HTTP/2 + fragment'}" if protocol == "masque"
                             else {"wg": "WireGuard", "gool": "WARP-in-WARP (gool)",
                                   "wom": f"WireGuard over MASQUE {mode.upper()}"}.get(protocol, protocol)) + f", IPv{family}",
                    "tor": f"Tor inside MASQUE {mode.upper()}", "tor-only": "Tor alone",
                    "psiphon": f"Psiphon inside MASQUE {mode.upper()}", "psiphon-only": "Psiphon alone"}[kind]
            progress(f"Starting Aether ({what}) on port {use} - the first start can take a few minutes ...")
            self._launch(port, mode, tor=kind if kind.startswith("tor") else None, tor_port=side_port if kind == "tor" else None,
                         protocol=protocol, family=family, psiphon=kind if kind.startswith("psiphon") else None,
                         psiphon_port=side_port if kind == "psiphon" else None, region=region)
            if self.last_notice:
                progress(self.last_notice); self.last_notice = ""
            proc = self.process
            end = time.time() + wait
            check = ready if (ready is not socks_ready or kind == "warp") else socks_tunnel_ok
            while time.time() < end:
                if cancelled():
                    self.stop(); raise AetherError("cancelled")
                if self.process is not proc:                     # Disconnect / another connect stopped it while it was starting
                    raise AetherError("cancelled")
                if proc.poll() is not None:
                    break
                if check(use):
                    self.port, self.kind = use, kind
                    return use
                sleep(0.5)
            progress("Aether did not become ready" + (" - trying the next mode" if mode != modes[-1] and kind not in ONLY_KINDS else ""))
            self.stop()
        tail = "\n".join(self.tail())
        if kind != "warp" and re.search(r"unexpected argument|unknown (option|argument)|not (built|compiled)|unrecognized", tail, re.I):
            what = "Psiphon" if kind.startswith("psiphon") else "Tor"
            raise AetherError(f"this Aether build has no {what} support. Last output:\n" + tail)
        if kind.startswith("psiphon") and re.search(r"psiphon.{0,40}(not found|no such file|cannot find|missing)", tail, re.I):
            raise AetherError("the Psiphon program (pt/psiphon-tunnel-core) was not found next to aether.exe. Download the Aether core again. Last output:\n" + tail)
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


def psiphon_profile(port=DEFAULT_PORT, kind="psiphon"):
    return {"type": "socks", "name": "Psiphon (Aether)" if kind == "psiphon" else "Psiphon alone (Aether)", "server": "127.0.0.1",
            "port": int(port), "group": "Psiphon", "engine": "aether", "aether_kind": kind, "security": "", "network": "tcp"}


def needs_kind(profile):
    return profile.get("aether_kind", "warp") if is_aether(profile) else None


def is_aether(profile):
    return isinstance(profile, dict) and profile.get("engine") == "aether"
