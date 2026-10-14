from urllib.parse import urlparse, parse_qs, unquote
from app.utils.params import extract_extra

def parse_trojan(uri):
    u = urlparse(uri.strip())
    if u.scheme.lower() != "trojan":
        raise ValueError("Not a Trojan URI")
    q = parse_qs(u.query)
    get = lambda k, d="": q.get(k, [d])[0]
    prof = {
        "name": unquote(u.fragment) or f"{u.hostname}:{u.port}",
        "type": "trojan", "server": u.hostname, "port": u.port or 443,
        "password": unquote(u.username or ""),
        "network": get("type", "tcp"), "security": get("security", "tls"),
        "sni": get("sni", ""), "host": get("host", ""), "path": get("path", ""),
        "fp": get("fp", "")
    }
    prof.update(extract_extra(q))
    return prof
