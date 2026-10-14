from urllib.parse import urlparse, unquote
import base64

# Methods the bundled Xray accepts (checked with `xray run -test`).
SS_METHODS = {
    "aes-128-gcm", "aes-256-gcm", "chacha20-poly1305", "chacha20-ietf-poly1305",
    "xchacha20-poly1305", "xchacha20-ietf-poly1305",
    "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305",
}

def fix_ss(method, password):
    """Some converters write method 'none' and hide 'method:password' inside the base64 password."""
    if method in ("none", "plain", ""):
        raw = password + "=" * (-len(password) % 4)
        for dec in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                txt = dec(raw).decode()
            except Exception:
                continue
            m, _, pw = txt.partition(":")
            if pw and m in SS_METHODS:
                return m, pw
    return method, password

def parse_shadowsocks(uri):
    u = urlparse(uri.strip())
    if u.scheme.lower() != "ss":
        raise ValueError("Not a Shadowsocks URI")
    if "@" not in u.netloc and u.netloc:                    # legacy form: everything is inside the base64 part
        raw = unquote(u.netloc)
        raw += "=" * (-len(raw) % 4)
        try:
            legacy = base64.urlsafe_b64decode(raw).decode()
            cred, _, hostport = legacy.rpartition("@")
            host, _, port = hostport.rpartition(":")
            method, _, password = cred.partition(":")
            if host and port.isdigit() and password:
                method, password = fix_ss(method, password)
                return {"name": unquote(u.fragment) or f"{host}:{port}", "type": "shadowsocks",
                        "server": host.strip("[]"), "port": int(port), "method": method, "password": password}
        except Exception:
            pass
    user = unquote(u.username or "")
    if ":" not in user:
        raw = user + "=" * (-len(user) % 4)
        try:
            user = base64.urlsafe_b64decode(raw).decode()
        except Exception:
            pass
    if ":" not in user:
        raise ValueError("Invalid Shadowsocks credentials")
    method, password = user.split(":", 1)
    method, password = fix_ss(method, password)
    return {
        "name": unquote(u.fragment) or f"{u.hostname}:{u.port}",
        "type": "shadowsocks", "server": u.hostname, "port": u.port or 8388,
        "method": method, "password": password
    }
