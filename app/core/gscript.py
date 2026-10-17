"""Google Script relay: web requests are sent to YOUR OWN Google Apps Script web app (assets/gscript/Code.gs), which fetches them.

The connection to Google looks like ordinary Google traffic: TCP goes to a Google address, TLS SNI is a Google name (default
www.google.com) and the real target (script.google.com) is only in the encrypted Host header.

NetBridge talks to this relay through a local SOCKS5 port (same shape as the Aether WARP core). Because Apps Script can only fetch
URLs, HTTPS sites are decrypted locally with a certificate authority generated on this PC (ca.pem). Only port 80/443 web traffic
works: no UDP, no WebSocket, no other protocols.
Everything that can be tested without a network is a plain function.
"""
import base64
import datetime
import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
import struct
import subprocess
import threading
import urllib.parse
from pathlib import Path

DATA_DIR = Path("data/gscript")
CODE_GS = Path(__file__).resolve().parent.parent.parent / "assets" / "gscript" / "Code.gs"
DEFAULT_PORT = 1830
FRONT_DEFAULT = "www.google.com"
MAX_BODY = 20 * 1024 * 1024
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DROP_REQ = {"host", "connection", "proxy-connection", "proxy-authorization", "keep-alive", "te", "trailer", "upgrade",
            "content-length", "accept-encoding", "transfer-encoding", "expect"}
DROP_RESP = {"transfer-encoding", "content-encoding", "content-length", "connection", "keep-alive", "proxy-connection"}
SCRIPT_URL_RE = re.compile(r"^https://script\.google(?:usercontent)?\.com/macros/s/[A-Za-z0-9_\-]{10,200}/exec$")


class GScriptError(Exception):
    pass


# ------------------------------------------------------------------ the script text and settings
def new_key():
    return secrets.token_urlsafe(18)


def code_gs(key):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{8,64}", key or ""):
        raise GScriptError("the secret key may contain only letters, digits, - and _ (8-64 characters)")
    return CODE_GS.read_text(encoding="utf-8").replace("__AUTH_KEY__", key)


def check_settings(script_url, key, google_ip="", front=FRONT_DEFAULT):
    script_url = (script_url or "").strip()
    if not SCRIPT_URL_RE.match(script_url):
        raise GScriptError("the script address must look like https://script.google.com/macros/s/.../exec")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{8,64}", key or ""):
        raise GScriptError("the secret key must match the one in Code.gs (letters, digits, - and _)")
    google_ip = (google_ip or "").strip()
    if google_ip:
        try:
            ipaddress.ip_address(google_ip)
        except ValueError:
            raise GScriptError("the Google IP is not a valid address")
    if not re.fullmatch(r"[A-Za-z0-9.\-]{3,100}", front or ""):
        raise GScriptError("the front name is not valid")
    return {"script_url": script_url, "key": key, "google_ip": google_ip, "front": front}


def load_settings(data_dir=None):
    try:
        return json.loads((Path(data_dir or DATA_DIR) / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(cfg, data_dir=None):
    d = Path(data_dir or DATA_DIR); d.mkdir(parents=True, exist_ok=True)
    (d / "settings.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ messages to / from the script
def clean_headers(headers):
    return {k: v for k, v in headers.items() if k.lower() not in DROP_REQ}


def build_payload(key, method, url, headers, body=b""):
    p = {"k": key, "m": method, "u": url, "h": clean_headers(headers)}
    if body:
        p["b"] = base64.b64encode(body).decode()
    return json.dumps(p).encode()


def parse_reply(raw):
    """-> (status, [(name, value)...], body bytes). Raises GScriptError with a readable reason."""
    try:
        js = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise GScriptError("the script did not answer with JSON (wrong address, not deployed for 'Anyone', or Google blocked it)")
    if "e" in js:
        raise GScriptError("wrong secret key" if js["e"] == "auth" else f"script error: {js['e']}"[:200])
    hs = []
    for k, v in (js.get("h") or {}).items():
        if k.lower() in DROP_RESP:
            continue
        for item in (v if isinstance(v, list) else [v]):
            hs.append((k, str(item)))
    return int(js.get("s", 502)), hs, base64.b64decode(js.get("b") or "")


def response_bytes(status, headers, body):
    reason = http.client.responses.get(status, "OK")
    lines = [f"HTTP/1.1 {status} {reason}"] + [f"{k}: {v}" for k, v in headers]
    lines += [f"Content-Length: {len(body)}", "Connection: keep-alive", "", ""]
    return "\r\n".join(lines).encode("latin-1", "replace") + body


def read_request(f):
    """Reads one HTTP/1.x request from a binary file object. -> (method, target, headers dict, body) or None at end."""
    line = f.readline(65537)
    while line in (b"\r\n", b"\n"):
        line = f.readline(65537)
    if not line:
        return None
    parts = line.decode("latin-1").split()
    if len(parts) < 2:
        raise GScriptError("bad request line")
    method, target = parts[0], parts[1]
    headers = {}
    while True:
        h = f.readline(65537)
        if h in (b"\r\n", b"\n", b""):
            break
        if b":" in h:
            k, v = h.decode("latin-1").split(":", 1)
            headers[k.strip()] = v.strip()
    low = {k.lower(): v for k, v in headers.items()}
    body = b""
    if "chunked" in low.get("transfer-encoding", "").lower():
        chunks, total = [], 0
        while True:
            size = int(f.readline(100).split(b";")[0].strip() or b"0", 16)
            if size == 0:
                while f.readline(65537) not in (b"\r\n", b"\n", b""):
                    pass
                break
            total += size
            if total > MAX_BODY:
                raise GScriptError("request body too large")
            chunks.append(f.read(size)); f.readline(10)
        body = b"".join(chunks)
    elif low.get("content-length", "").isdigit():
        n = int(low["content-length"])
        if n > MAX_BODY:
            raise GScriptError("request body too large")
        body = f.read(n)
    return method, target, headers, body


def full_url(scheme, host, port, target, headers):
    if target.startswith(("http://", "https://")):
        return target
    h = next((v for k, v in headers.items() if k.lower() == "host"), host)
    default = 443 if scheme == "https" else 80
    if port != default and ":" not in h.rsplit("]", 1)[-1]:
        h = f"{h}:{port}"
    return f"{scheme}://{h}{target}"


# ------------------------------------------------------------------ talking to Google (fronted)
class Relay:
    def __init__(self, script_url, key, google_ip="", front=FRONT_DEFAULT, timeout=60):
        cfg = check_settings(script_url, key, google_ip, front)
        self.url, self.key, self.ip, self.front, self.timeout = cfg["script_url"], cfg["key"], cfg["google_ip"], cfg["front"], timeout
        self.ctx = ssl.create_default_context()

    def _open(self, host):
        raw = socket.create_connection((self.ip or self.front, 443), timeout=self.timeout)
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        tls = self.ctx.wrap_socket(raw, server_hostname=self.front)        # SNI = the front name; its certificate is verified
        conn = http.client.HTTPSConnection(host, 443, timeout=self.timeout)
        conn.sock = tls                                                     # the real name only appears in the Host header
        return conn

    def _roundtrip(self, method, url, body, headers):
        for _ in range(6):
            u = urllib.parse.urlsplit(url)
            conn = self._open(u.netloc)
            try:
                conn.request(method, u.path + ("?" + u.query if u.query else ""), body=body, headers=headers)
                r = conn.getresponse()
                data = r.read(MAX_BODY + 1)
                if r.status in (301, 302, 303, 307, 308) and r.getheader("Location"):
                    url, method, body, headers = urllib.parse.urljoin(url, r.getheader("Location")), "GET", None, {}
                    continue
                return r.status, data
            finally:
                conn.close()
        raise GScriptError("too many redirects from Google")

    def fetch(self, method, url, headers=None, body=b""):
        """One web request through the script. -> (status, [(name, value)], body)."""
        payload = build_payload(self.key, method, url, headers or {}, body)
        try:
            status, data = self._roundtrip("POST", self.url, payload, {"Content-Type": "application/json"})
        except (OSError, ssl.SSLError, http.client.HTTPException) as e:
            raise GScriptError(f"cannot reach Google: {e}")
        if status != 200:
            raise GScriptError(f"Google answered HTTP {status} (check that the deployment is set to 'Anyone')")
        return parse_reply(data)

    def test(self):
        s, _, _ = self.fetch("GET", "https://www.gstatic.com/generate_204")
        if s not in (200, 204):
            raise GScriptError(f"test request returned HTTP {s}")
        return True


# ------------------------------------------------------------------ the local certificate authority
def _crypto():
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        raise GScriptError("the 'cryptography' package is missing (pip install cryptography)")
    return x509, hashes, serialization, ec, rsa, NameOID


def ensure_ca(data_dir=None):
    """Creates (once) the local CA. -> (ca_cert_path, ca_key_path). The key never leaves this folder."""
    d = Path(data_dir or DATA_DIR); d.mkdir(parents=True, exist_ok=True)
    cert_p, key_p = d / "ca.pem", d / "ca.key"
    if cert_p.exists() and key_p.exists():
        return cert_p, key_p
    x509, hashes, ser, ec, rsa, N = _crypto()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(N.COMMON_NAME, "NetBridge Google Script local CA"), x509.NameAttribute(N.ORGANIZATION_NAME, "NetBridge")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    key_p.write_bytes(key.private_bytes(ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption()))
    cert_p.write_bytes(cert.public_bytes(ser.Encoding.PEM))
    return cert_p, key_p


def make_leaf(host, ca_cert_pem, ca_key_pem):
    """A short-lived certificate for `host`, signed by the local CA. -> (cert_pem, key_pem) bytes."""
    x509, hashes, ser, ec, rsa, N = _crypto()
    ca = x509.load_pem_x509_certificate(ca_cert_pem)
    ca_key = ser.load_pem_private_key(ca_key_pem, None)
    key = ec.generate_private_key(ec.SECP256R1())
    try:
        san = x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        san = x509.DNSName(host)
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(N.COMMON_NAME, host[:60])]))
            .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=300))
            .add_extension(x509.SubjectAlternativeName([san]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    return (cert.public_bytes(ser.Encoding.PEM),
            key.private_bytes(ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption()))


def install_ca_args(ca_path):
    """Windows: adds the CA to the CURRENT USER's trusted roots (Windows shows its own confirmation window)."""
    return ["certutil", "-user", "-addstore", "Root", str(ca_path)]


def install_ca(ca_path):
    r = subprocess.run(install_ca_args(ca_path), capture_output=True, text=True, creationflags=NOWIN)
    if r.returncode != 0:
        raise GScriptError("the certificate was not installed: " + (r.stdout + r.stderr).strip()[-200:])


# ------------------------------------------------------------------ the local SOCKS5 server
class GScriptServer:
    def __init__(self, relay, data_dir=None, port=DEFAULT_PORT):
        self.relay, self.dir, self.port = relay, Path(data_dir or DATA_DIR), port
        self.sock = None
        self.requests = 0
        self.last_error = ""
        self._ctx = {}
        self._lock = threading.Lock()
        self._stop = False

    @property
    def running(self):
        return self.sock is not None

    def start(self):
        ca_cert, ca_key = ensure_ca(self.dir)
        self._ca = (ca_cert.read_bytes(), ca_key.read_bytes())
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", self.port)); self.sock.listen(64)
        self._stop = False
        threading.Thread(target=self._accept, daemon=True).start()
        return self.port

    def stop(self):
        self._stop = True
        s, self.sock = self.sock, None
        if s:
            try: s.close()
            except OSError: pass

    def _accept(self):
        sock = self.sock
        while not self._stop and sock:
            try:
                c, _ = sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(c,), daemon=True).start()

    def _server_ctx(self, host):
        with self._lock:
            ctx = self._ctx.get(host)
            if ctx is None:
                cert, key = make_leaf(host, *self._ca)
                d = self.dir / "leaf"; d.mkdir(parents=True, exist_ok=True)
                p = d / (re.sub(r"[^A-Za-z0-9.\-]", "_", host) + ".pem")
                p.write_bytes(cert + key)
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.set_alpn_protocols(["http/1.1"])
                ctx.load_cert_chain(str(p))
                self._ctx[host] = ctx
            return ctx

    def _client(self, c):
        try:
            c.settimeout(30)
            if c.recv(1)[:1] != b"\x05":
                return
            n = c.recv(1)[0]; c.recv(n); c.sendall(b"\x05\x00")
            ver, cmd, _, atyp = c.recv(4)
            if atyp == 1:
                host = socket.inet_ntoa(c.recv(4))
            elif atyp == 3:
                host = c.recv(c.recv(1)[0]).decode("ascii", "replace")
            elif atyp == 4:
                host = socket.inet_ntop(socket.AF_INET6, c.recv(16))
            else:
                return
            port = struct.unpack(">H", c.recv(2))[0]
            if cmd != 1 or port not in (80, 443):                  # only web traffic can go through a script
                c.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00"); return
            c.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            scheme = "http"
            if port == 443:
                c = self._server_ctx(host).wrap_socket(c, server_side=True); scheme = "https"
            self._serve(c, scheme, host, port)
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"[:200]
        finally:
            try: c.close()
            except OSError: pass

    def _serve(self, c, scheme, host, port):
        f = c.makefile("rb")
        c.settimeout(60)
        while True:
            req = read_request(f)
            if req is None:
                return
            method, target, headers, body = req
            low = {k.lower(): v for k, v in headers.items()}
            if "upgrade" in low:                                    # WebSocket cannot pass through a script
                c.sendall(response_bytes(501, [("Content-Type", "text/plain")], b"WebSocket is not supported by the Google Script relay"))
                return
            try:
                status, hs, data = self.relay.fetch(method, full_url(scheme, host, port, target, headers), headers, body)
                self.requests += 1
            except GScriptError as e:
                self.last_error = str(e)
                status, hs, data = 502, [("Content-Type", "text/plain; charset=utf-8")], f"NetBridge Google Script: {e}".encode()
            if method.upper() == "HEAD":
                data = b""
            c.sendall(response_bytes(status, hs, data))


def local_profile(port=DEFAULT_PORT):
    return {"type": "socks", "name": "Google Script", "server": "127.0.0.1", "port": int(port), "group": "Google Script",
            "engine": "gscript", "security": "", "network": "tcp"}


def is_gscript(profile):
    return isinstance(profile, dict) and profile.get("engine") == "gscript"
