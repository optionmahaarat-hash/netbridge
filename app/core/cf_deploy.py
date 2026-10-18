"""One-click deploy of a personal VLESS relay to the user's OWN Cloudflare account (free plan, workers.dev address).

Uses a scoped API token (permission: Account > Workers Scripts > Edit; Workers subdomain access is part of it). The token is
used only for the calls below and is never written to disk. Everything network-related goes through `call`, so it is testable.
"""
import json
import re
import secrets
import urllib.error
import urllib.request
import uuid as uuidlib
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
WORKER_SRC = Path(__file__).resolve().parent.parent.parent / "assets" / "worker" / "vless_worker.js"
COMPAT_DATE = "2025-01-01"
TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{20,120}$")


class DeployError(Exception):
    pass


def worker_source(uuid_str):
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", uuid_str):
        raise DeployError("bad UUID")
    return WORKER_SRC.read_text(encoding="utf-8").replace("__UUID__", uuid_str)


def random_name(prefix="nb"):
    return f"{prefix}-{secrets.token_hex(4)}"


def multipart(source, bindings=None):
    """(body, content_type) for the module upload: a JSON 'metadata' part plus the 'worker.js' module.
    bindings: optional list such as [{"type": "secret_text", "name": "SECRET", "text": "..."}]."""
    b = "----nb" + secrets.token_hex(12)
    md = {"main_module": "worker.js", "compatibility_date": COMPAT_DATE}
    if bindings:
        md["bindings"] = list(bindings)
    meta = json.dumps(md)
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n{meta}\r\n',
             f'--{b}\r\nContent-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
             f'Content-Type: application/javascript+module\r\n\r\n{source}\r\n', f'--{b}--\r\n']
    return "".join(parts).encode("utf-8"), f"multipart/form-data; boundary={b}"


def call(method, path, token, body=None, content_type="application/json", timeout=30, proxy=None):
    """One Cloudflare API call. Returns the parsed 'result'. Raises DeployError with Cloudflare's own message."""
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": content_type, "User-Agent": "NetBridge"})
    handlers = [urllib.request.ProxyHandler({"https": proxy, "http": proxy})] if proxy else []
    try:
        with urllib.request.build_opener(*handlers).open(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
    except OSError as e:
        raise DeployError(f"cannot reach Cloudflare: {e}")
    try:
        js = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise DeployError("unexpected answer from Cloudflare")
    if not js.get("success"):
        errs = "; ".join(str(e.get("message", e)) for e in js.get("errors", [])) or "unknown error"
        raise DeployError(errs)
    return js.get("result")


def deploy(token, name=None, uuid_str=None, call=call, progress=lambda s: None):
    """Creates the worker and turns on its workers.dev address. Returns a NetBridge profile dict.
    `call(method, path, token, body=None, content_type=...)` is replaceable for tests."""
    token = (token or "").strip()
    if not TOKEN_RE.match(token):
        raise DeployError("that does not look like a Cloudflare API token")
    name = name or random_name()
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,40}", name):
        raise DeployError("worker name may contain only a-z, 0-9 and '-'")
    uuid_str = uuid_str or str(uuidlib.uuid4())
    progress("Checking the token ...")
    call("GET", "/user/tokens/verify", token)
    accounts = call("GET", "/accounts", token) or []
    if not accounts:
        raise DeployError("the token has no access to any account (add Account > Workers Scripts > Edit and Account Settings > Read)")
    acc = accounts[0]["id"]
    progress("Uploading the worker ...")
    body, ctype = multipart(worker_source(uuid_str))
    call("PUT", f"/accounts/{acc}/workers/scripts/{name}", token, body, ctype, timeout=60)
    progress("Turning on the workers.dev address ...")
    sub = (call("GET", f"/accounts/{acc}/workers/subdomain", token) or {}).get("subdomain")
    if not sub:
        sub = f"nb-{secrets.token_hex(4)}"
        call("PUT", f"/accounts/{acc}/workers/subdomain", token, {"subdomain": sub})
    call("POST", f"/accounts/{acc}/workers/scripts/{name}/subdomain", token, {"enabled": True, "previews_enabled": False})
    host = f"{name}.{sub}.workers.dev"
    return {"type": "vless", "name": f"Mine - {name}", "server": host, "port": 443, "network": "ws", "uuid": uuid_str,
            "security": "tls", "sni": host, "host": host, "path": "/", "fp": "chrome", "alpn": "http/1.1",
            "group": "My Worker"}
