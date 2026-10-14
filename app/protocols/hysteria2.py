from urllib.parse import urlparse, parse_qs, unquote

def parse_hysteria2(uri):
    u = urlparse(uri.strip())
    if u.scheme.lower() not in ("hysteria2", "hy2"):
        raise ValueError("Not a Hysteria2 URI")
    q = parse_qs(u.query)
    get = lambda k, d="": unquote(q.get(k, [d])[0])
    auth = unquote(u.username or "")
    if u.password: auth += ":" + unquote(u.password)
    p = {"name": unquote(u.fragment) or f"{u.hostname}:{u.port}", "type": "hysteria2",
         "server": u.hostname, "port": u.port or 443, "password": auth,
         "network": "hysteria", "security": "tls", "sni": get("sni")}
    if get("insecure") == "1" or get("allowInsecure") == "1": p["insecure"] = True
    if get("pcs") or get("pinSHA256"): p["pcs"] = get("pcs") or get("pinSHA256")
    if get("obfs-password"): p["obfs_password"] = get("obfs-password")
    return p
