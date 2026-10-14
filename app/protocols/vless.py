from urllib.parse import urlparse, parse_qs, unquote
import uuid
from app.utils.params import extract_extra

def parse_vless(uri):
    u = urlparse(uri.strip())
    if u.scheme.lower() != "vless":
        raise ValueError("Not a VLESS URI")
    user = unquote(u.username or "")
    try:
        uuid.UUID(user)
    except Exception:
        raise ValueError("Invalid VLESS UUID")
    q = parse_qs(u.query)
    get = lambda k, d="": q.get(k, [d])[0]
    prof = {
        "name": unquote(u.fragment) or f"{u.hostname}:{u.port}",
        "type": "vless", "server": u.hostname, "port": u.port, "uuid": user,
        "network": get("type", "tcp"), "security": get("security", ""),
        "sni": get("sni", ""), "host": get("host", ""), "path": get("path", ""),
        "fp": get("fp", ""), "alpn": get("alpn", ""), "flow": get("flow", "")
    }
    prof.update(extract_extra(q))
    return prof
