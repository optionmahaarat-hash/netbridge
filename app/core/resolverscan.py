"""DNS resolver finder: which public resolvers answer from THIS network, and over which transport.

Each resolver is tried over plain UDP, plain TCP, DNS-over-TLS (853) and DNS-over-HTTPS. A real A query is sent and the
answer must be a valid reply to that query, so a captive or poisoned reply that does not echo our query id is rejected.
Everything here is written from scratch for NetBridge; nothing leaves the machine except the queries themselves.
"""
import base64
import socket
import ssl
import struct
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

QUERY_NAME = "www.google.com"
PROTOCOLS = ("udp", "tcp", "dot", "doh")

# (label, ip, DoH url or None, TLS server name for DoT/DoH or None)
RESOLVERS = [
    ("Cloudflare", "1.1.1.1", "https://1.1.1.1/dns-query", "one.one.one.one"),
    ("Cloudflare 2", "1.0.0.1", "https://1.0.0.1/dns-query", "one.one.one.one"),
    ("Google", "8.8.8.8", "https://8.8.8.8/dns-query", "dns.google"),
    ("Google 2", "8.8.4.4", "https://8.8.4.4/dns-query", "dns.google"),
    ("Quad9", "9.9.9.9", "https://9.9.9.9/dns-query", "dns.quad9.net"),
    ("Quad9 2", "149.112.112.112", "https://149.112.112.112/dns-query", "dns.quad9.net"),
    ("OpenDNS", "208.67.222.222", "https://208.67.222.222/dns-query", "dns.opendns.com"),
    ("AdGuard", "94.140.14.14", "https://94.140.14.14/dns-query", "dns.adguard-dns.com"),
    ("CleanBrowsing", "185.228.168.9", None, "security-filter-dns.cleanbrowsing.org"),
    ("Shecan", "178.22.122.100", None, None),
    ("Electro", "78.157.42.100", None, None),
    ("Radar", "10.202.10.10", None, None),
]


def build_query(name=QUERY_NAME, qid=None):
    qid = int(time.time() * 1000) & 0xFFFF if qid is None else qid
    q = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    for part in name.split("."):
        q += bytes([len(part)]) + part.encode()
    return qid, q + b"\x00" + struct.pack(">HH", 1, 1)


def valid_reply(data, qid):
    """A reply to OUR query: same id, QR bit set, no error, at least one answer."""
    if len(data) < 12:
        return False
    rid, flags, _qd, an = struct.unpack(">HHHH", data[:8])
    return rid == qid and bool(flags & 0x8000) and (flags & 0xF) == 0 and an > 0


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise OSError("closed")
        buf += chunk
    return buf


def test_udp(ip, timeout=2.5):
    qid, q = build_query()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(q, (ip, 53))
        return valid_reply(s.recv(2048), qid)


def test_tcp(ip, timeout=3.0):
    qid, q = build_query()
    with socket.create_connection((ip, 53), timeout) as s:
        s.settimeout(timeout)
        s.sendall(struct.pack(">H", len(q)) + q)
        n = struct.unpack(">H", _recv_exact(s, 2))[0]
        return valid_reply(_recv_exact(s, n), qid)


def test_dot(ip, sni=None, timeout=4.0):
    qid, q = build_query()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False          # we only need to know the path works; many resolvers answer by IP
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((ip, 853), timeout) as raw:
        raw.settimeout(timeout)
        with ctx.wrap_socket(raw, server_hostname=sni or ip) as s:
            s.sendall(struct.pack(">H", len(q)) + q)
            n = struct.unpack(">H", _recv_exact(s, 2))[0]
            return valid_reply(_recv_exact(s, n), qid)


def test_doh(url, timeout=4.0):
    qid, q = build_query()
    dns = base64.urlsafe_b64encode(q).decode().rstrip("=")
    req = urllib.request.Request(f"{url}?dns={dns}", headers={"Accept": "application/dns-message", "User-Agent": "NetBridge"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # never through our own proxy
    with opener.open(req, timeout=timeout) as r:
        return r.status == 200 and valid_reply(r.read(4096), qid)


def _timed(fn, *a):
    t = time.time()
    try:
        ok = fn(*a)
    except Exception:
        ok = False
    return int((time.time() - t) * 1000) if ok else -1


def probe(resolver, protocols=PROTOCOLS, tests=None):
    """Returns {"label", "ip", "doh_url", "udp"/"tcp"/"dot"/"doh": ms|-1}. `tests` can replace the network functions (for unit tests)."""
    label, ip, doh, sni = resolver
    t = tests or {"udp": test_udp, "tcp": test_tcp, "dot": test_dot, "doh": test_doh}
    out = {"label": label, "ip": ip, "doh_url": doh}
    for proto in protocols:
        if proto == "udp" or proto == "tcp":
            out[proto] = _timed(t[proto], ip)
        elif proto == "dot":
            out[proto] = _timed(t["dot"], ip, sni)
        elif proto == "doh":
            out[proto] = _timed(t["doh"], doh) if doh else -1
    return out


def best_ms(row, protocols=PROTOCOLS):
    ok = [row[p] for p in protocols if row.get(p, -1) >= 0]
    return min(ok) if ok else None


def scan(resolvers=None, protocols=PROTOCOLS, workers=8, cancelled=lambda: False, on_row=lambda r: None, tests=None):
    """Probes every resolver in parallel; rows with at least one working transport come first, fastest first."""
    items = list(resolvers or RESOLVERS)

    def one(r):
        if cancelled():
            return None
        row = probe(r, protocols, tests)
        on_row(row)
        return row

    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = [r for r in ex.map(one, items) if r]
    rows.sort(key=lambda r: (best_ms(r, protocols) is None, best_ms(r, protocols) or 0))
    return rows


def working_doh(rows):
    """DoH URLs that answered, fastest first - what AUTO should use for the ECH key lookup."""
    ok = [r for r in rows if r.get("doh_url") and r.get("doh", -1) >= 0]
    return [r["doh_url"] for r in sorted(ok, key=lambda r: r["doh"])]
