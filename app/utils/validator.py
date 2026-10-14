from app.protocols.shadowsocks import SS_METHODS

REQUIRED = ["name", "server", "port"]

def validate_profile(p):
    errors = []
    for k in REQUIRED:
        if not p.get(k):
            errors.append(f"Missing: {k}")
    try:
        port = int(p.get("port", 0))
        if not 1 <= port <= 65535:
            errors.append("Invalid port")
    except Exception:
        errors.append("Invalid port")
    if p.get("type") not in {"vless", "vmess", "trojan", "shadowsocks", "hysteria2"}:
        errors.append("Unsupported protocol")
    if str(p.get("server", "")).strip() in ("0.0.0.0", "127.0.0.1", "localhost"):
        errors.append("Fake server address")
    if p.get("type") == "shadowsocks" and p.get("method") not in SS_METHODS:
        errors.append(f"Shadowsocks method not supported: {p.get('method')}")
    if p.get("type") == "hysteria2" and not p.get("password"):
        errors.append("Hysteria2 needs a password")
    if p.get("security") == "reality" and not p.get("pbk"):
        errors.append("Reality needs a public key")
    return errors
