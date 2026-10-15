"""Clean-IP scanner for Cloudflare-based profiles (Workers / Pages / CDN).

For each sampled Cloudflare IP we do the same thing your client does:
TCP connect -> TLS handshake with your profile's SNI -> HTTP GET /cdn-cgi/trace with Host = your domain.
An IP that answers is reachable from YOUR ISP right now; the time is the real latency.
The IP found is only the ENTRY point (put it in the profile's 'Clean IP'). The EXIT of a
Workers config stays Cloudflare, so this does not change what websites see.
"""
import ipaddress
import random
import socket
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

CF_PORTS = {443, 8443, 2053, 2083, 2087, 2096}
RANGES_URL = "https://www.cloudflare.com/ips-v4"
RANGES6_URL = "https://www.cloudflare.com/ips-v6"

# Cloudflare's published IPv4 ranges (fallback when the list cannot be downloaded)
FALLBACK_RANGES = [
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
]


# Cloudflare's published IPv6 ranges (fallback). The IPv4 restriction reported in the PattNG channel (upload limit
# of ~6 packets, IPv4 only so far) makes an IPv6 entry point worth trying - when this phone/PC really has IPv6.
FALLBACK_RANGES6 = [
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
    "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
]


def _load(url, fallback, version, timeout):
    try:
        t = urllib.request.urlopen(url, timeout=timeout).read().decode()
        r = [x.strip() for x in t.splitlines() if "/" in x]
        if not r or any(ipaddress.ip_network(x).version != version for x in r):
            raise ValueError("unexpected list")
        return r
    except Exception:
        return list(fallback)


def load_ranges(timeout=6):
    """Official IPv4 list if reachable, else the built-in one."""
    return _load(RANGES_URL, FALLBACK_RANGES, 4, timeout)


def load_ranges6(timeout=6):
    """Official IPv6 list if reachable, else the built-in one."""
    return _load(RANGES6_URL, FALLBACK_RANGES6, 6, timeout)


def has_ipv6():
    """True if this machine has an IPv6 route to the internet. Nothing is sent: a UDP connect() only asks the routing table."""
    s = None
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.connect(("2606:4700:4700::1111", 53))
        return True
    except OSError:
        return False
    finally:
        if s is not None:
            s.close()


def is_ipv6(ip):
    return ":" in str(ip)


def _sample(nets, n, rng):
    sizes = [net.num_addresses for net in nets]
    out, tries = set(), 0
    while len(out) < n and tries < n * 20:
        tries += 1
        net = rng.choices(nets, weights=sizes)[0]
        if net.num_addresses < 4:
            continue
        out.add(str(net[rng.randrange(1, net.num_addresses - 1)]))   # skip network / broadcast
    return list(out)


def sample_ips(ranges, n, rng=random, v6_share=0.5):
    """n distinct random IPs, spread over the ranges proportionally to their size.
    With both IPv4 and IPv6 ranges, `v6_share` of the IPs are IPv6 (an IPv6 range is billions of times bigger,
    so by size alone it would crowd out IPv4 completely); inside each family the spread is by size."""
    nets = [ipaddress.ip_network(r) for r in ranges]
    v4 = [x for x in nets if x.version == 4]
    v6 = [x for x in nets if x.version == 6]
    if v4 and v6:
        n6 = int(n * v6_share)
        return _sample(v4, n - n6, rng) + _sample(v6, n6, rng)
    return _sample(nets, n, rng)


def parse_trace(text):
    return dict(l.split("=", 1) for l in text.splitlines() if "=" in l)


def probe(ip, port, sni, timeout=3.0):
    """Returns (ms, colo) or None. ms covers connect + TLS + one HTTP round trip."""
    t0 = time.perf_counter()
    try:
        raw = socket.create_connection((ip, port), timeout=timeout)
    except Exception:
        return None
    s = None
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False          # we test reachability, not identity
        ctx.verify_mode = ssl.CERT_NONE
        s = ctx.wrap_socket(raw, server_hostname=sni or None)
        s.settimeout(timeout)
        host = sni or ip
        s.sendall(f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {host}\r\nUser-Agent: NetBridge\r\nConnection: close\r\n\r\n".encode())
        data = b""
        while len(data) < 4096:
            chunk = s.recv(2048)
            if not chunk:
                break
            data += chunk
        ms = int((time.perf_counter() - t0) * 1000)
        head, _, body = data.decode("utf-8", "replace").partition("\r\n\r\n")
        if " 200" not in head.split("\r\n", 1)[0]:
            return None
        tr = parse_trace(body)
        if "colo" not in tr:
            return None
        return ms, tr["colo"]
    except Exception:
        return None
    finally:
        for sock in (s, raw):               # wrap_socket() detaches `raw`, so the TLS socket must be closed itself
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass


def probe_best(ip, port, sni, timeout=3.0, tries=2):
    """Best of a few tries; an IP must answer at least once."""
    best = None
    for _ in range(tries):
        r = probe(ip, port, sni, timeout)
        if r and (best is None or r[0] < best[0]):
            best = r
    return best


def scan(ips, port, sni, on_result, on_progress=None, cancelled=lambda: False, workers=60, timeout=3.0):
    """on_result(ip, ms, colo) for each working IP. Returns the number of IPs tried."""
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(lambda i=i: None if cancelled() else probe_best(i, port, sni, timeout)): i for i in ips}
        for f in as_completed(futs):
            done += 1
            try:
                r = f.result()
            except Exception:
                r = None
            if r:
                on_result(futs[f], r[0], r[1])
            if on_progress:
                on_progress(done, len(ips))
            if cancelled():
                for g in futs:
                    g.cancel()
    return done


def scan_target(profile):
    """(port, sni) to probe for a profile."""
    port = int(profile.get("port") or 443)
    sni = profile.get("sni") or profile.get("host") or profile.get("server") or ""
    return port, sni


def looks_cloudflare(profile):
    return str(profile.get("security", "")).lower() in ("tls",) and int(profile.get("port") or 0) in CF_PORTS
