"""Convert plain (no TLS) profiles to TLS - ONLY where the server really offers TLS.

A client cannot add TLS to a server that does not speak it. What it can do is look for a TLS door:
  1. the same port (some panels run TLS on the advertised port but export 'security=none'),
  2. the usual TLS ports of the same host (443, 8443, 2053, 2083, 2087, 2096): this is the classic
     fix for Cloudflare-fronted configs exported on the HTTP ports (80, 8080, 8880, 2052, 2082, 2086, 2095).
Every candidate must (a) answer a TLS handshake and (b) really work: it is started in a private Xray and
asked for the exit IP. Only candidates that pass both are returned.
"""
import hashlib
import ipaddress
import socket
import ssl

TLS_PORTS = [443, 8443, 2053, 2083, 2087, 2096]
PLAIN = ("", "none")
SUPPORTED = ("vless", "vmess", "trojan")


def is_plain(p):
    return p.get("type") in SUPPORTED and (p.get("security") or "") in PLAIN


def _is_ip(s):
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def tls_name(p):
    """The name to present in the TLS handshake (SNI): explicit sni, else the ws Host header, else a domain server."""
    n = p.get("sni") or p.get("host") or ""
    if not n and p.get("server") and not _is_ip(p["server"]):
        n = p["server"]
    return n


def candidate_ports(p):
    out = [int(p["port"])]
    for x in TLS_PORTS:
        if x not in out:
            out.append(x)
    return out


def handshake(host, port, sni="", timeout=4.0):
    """None if the port does not speak TLS, else {'verified': bool, 'hash': sha256 hex of the leaf certificate}."""
    der = None
    verified = False
    if sni:
        try:                                    # certificate valid for this name?
            ctx = ssl.create_default_context()
            with socket.create_connection((host, int(port)), timeout=timeout) as s:
                with ctx.wrap_socket(s, server_hostname=sni) as t:
                    der, verified = t.getpeercert(binary_form=True), True
        except Exception:
            der = None
    if der is None:
        try:                                    # self-signed or other name: we will pin it
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((host, int(port)), timeout=timeout) as s:
                with ctx.wrap_socket(s, server_hostname=sni or None) as t:
                    der = t.getpeercert(binary_form=True)
        except Exception:
            return None
    return {"verified": verified, "hash": hashlib.sha256(der).hexdigest()}


def make_tls_profile(p, port, hs):
    q = dict(p)
    q["port"] = port
    q["security"] = "tls"
    sni = tls_name(p)
    if sni:
        q["sni"] = sni
    if not q.get("fp"):
        q["fp"] = "chrome"
    if q.get("network") == "ws" and not q.get("alpn"):
        q["alpn"] = "http/1.1"          # a Chrome-like hello offers h2; a WebSocket needs http/1.1
    if hs["verified"]:
        q.pop("insecure", None); q.pop("pcs", None)
    else:
        q["insecure"] = True
        q["pcs"] = hs["hash"]
    q["name"] = f"{p.get('name', 'profile')} [TLS {port}]"
    q.pop("delay", None); q.pop("pin_failed", None)
    return q


def find_tls(p, works, handshake_fn=handshake):
    """Returns (new_profile, info) for the first candidate that handshakes AND passes works(profile) -> info/None,
    or (None, reason)."""
    if not is_plain(p):
        return None, "already TLS / not supported"
    sni = tls_name(p)
    seen_tls = False
    for port in candidate_ports(p):
        hs = handshake_fn(p["server"], port, sni)
        if not hs:
            continue
        seen_tls = True
        q = make_tls_profile(p, port, hs)
        info = works(q)
        if info:
            return q, info
    return None, ("TLS answers but the proxy does not work on it" if seen_tls
                  else "this server offers no TLS port (it only speaks plain). It cannot be converted.")
