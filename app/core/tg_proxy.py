"""Telegram "web proxy" on the user's OWN Cloudflare account.

Runs the open-source Worker ToiCF/CF-Workers-TGProxy (GPL-3.0, one file: telegram_webproxy.js). It is NOT bundled with NetBridge:
it is downloaded from the project's own repository when you press the button, exactly like the Aether core.

What the Worker needs: two secrets, SECRET (32 hex characters) and BOOT (any random text). NetBridge makes both, uploads the Worker with them,
optionally attaches a custom domain that is already on the account, checks /health and builds the link
    https://t.me/webproxy?server=<domain>&secret=<SECRET>

The Cloudflare token is used only for the calls below and is never written to disk. Network calls go through `call`, so they are testable.
"""
import json
import re
import secrets
import urllib.error
import urllib.request

from app.core import cf_deploy
from app.core.cf_deploy import DeployError, TOKEN_RE

SOURCES = (
    "https://raw.githubusercontent.com/ToiCF/CF-Workers-TGProxy/main/telegram_webproxy.js",
    "https://cdn.jsdelivr.net/gh/ToiCF/CF-Workers-TGProxy@main/telegram_webproxy.js",
)
MAX_SOURCE = 2_000_000
LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]{0,40}[a-z0-9])?$")
HOST_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def gen_secret():
    return secrets.token_hex(16)          # 32 hex characters, same as `openssl rand -hex 16`


def gen_boot():
    return secrets.token_hex(24)          # 48 hex characters, same as `openssl rand -hex 24`


def link(server, secret):
    return f"https://t.me/webproxy?server={server}&secret={secret}"


def fetch_source(proxy=None, urls=SOURCES, timeout=30):
    """The Worker file from the project's own repository (first mirror that answers). Raises DeployError."""
    handlers = [urllib.request.ProxyHandler({"https": proxy, "http": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    last = "no address tried"
    for u in urls:
        try:
            with opener.open(urllib.request.Request(u, headers={"User-Agent": "NetBridge"}), timeout=timeout) as r:
                raw = r.read(MAX_SOURCE + 1)
        except (OSError, urllib.error.URLError) as e:
            last = str(e)
            continue
        if len(raw) > MAX_SOURCE:
            last = "file too large"
            continue
        text = raw.decode("utf-8", "replace")
        if "export default" not in text or "SECRET" not in text or "BOOT" not in text:
            last = "the file is not the expected Worker"
            continue
        return text
    raise DeployError(f"could not download the Telegram proxy Worker ({last})")


def list_zones(token, call=cf_deploy.call):
    """[(zone_id, name)] of the domains already on the account (needs Zone > Read; the 'Edit Cloudflare Workers' template has it)."""
    zs = call("GET", "/zones?per_page=50&status=active", token) or []
    return [(z["id"], z["name"]) for z in zs if z.get("id") and z.get("name")]


def hostname(label, zone_name):
    label = (label or "").strip().lower()
    if label in ("", "@"):
        host = zone_name.lower()
    else:
        if not LABEL_RE.match(label):
            raise DeployError("the sub-domain may contain only a-z, 0-9 and '-'")
        host = f"{label}.{zone_name.lower()}"
    if not HOST_RE.match(host):
        raise DeployError("that is not a valid domain name")
    return host


def deploy(token, source, zone=None, label="tg", name=None, call=cf_deploy.call, progress=lambda s: None):
    """Uploads the Worker with its two secrets, turns on workers.dev and, when `zone`=(zone_id, zone_name) is given,
    attaches <label>.<zone_name> as a custom domain. Returns a dict: name, secret, boot, workers_host, domain, server, link."""
    token = (token or "").strip()
    if not TOKEN_RE.match(token):
        raise DeployError("that does not look like a Cloudflare API token")
    name = name or cf_deploy.random_name("tg")
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,40}", name):
        raise DeployError("worker name may contain only a-z, 0-9 and '-'")
    host = hostname(label, zone[1]) if zone else None
    secret, boot = gen_secret(), gen_boot()
    progress("Checking the token ...")
    call("GET", "/user/tokens/verify", token)
    accounts = call("GET", "/accounts", token) or []
    if not accounts:
        raise DeployError("the token has no access to any account (use the 'Edit Cloudflare Workers' template)")
    acc = accounts[0]["id"]
    progress("Uploading the Telegram proxy Worker ...")
    body, ctype = cf_deploy.multipart(source, [{"type": "secret_text", "name": "SECRET", "text": secret},
                                              {"type": "secret_text", "name": "BOOT", "text": boot}])
    call("PUT", f"/accounts/{acc}/workers/scripts/{name}", token, body, ctype, timeout=60)
    progress("Turning on the workers.dev address ...")
    sub = cf_deploy.ensure_subdomain(call, acc, token)
    call("POST", f"/accounts/{acc}/workers/scripts/{name}/subdomain", token, {"enabled": True, "previews_enabled": False})
    workers_host = f"{name}.{sub}.workers.dev"
    domain = None
    if host:
        progress(f"Attaching {host} ...")
        call("PUT", f"/accounts/{acc}/workers/domains", token,
             {"hostname": host, "service": name, "zone_id": zone[0], "environment": "production"})
        domain = host
    server = domain or workers_host
    return {"name": name, "secret": secret, "boot": boot, "workers_host": workers_host, "domain": domain,
            "server": server, "link": link(server, secret)}


def health(server, proxy=None, timeout=15):
    """(ok, text): GET https://<server>/health must answer {"ok":true}."""
    handlers = [urllib.request.ProxyHandler({"https": proxy, "http": proxy})] if proxy else []
    try:
        with urllib.request.build_opener(*handlers).open(
                urllib.request.Request(f"https://{server}/health", headers={"User-Agent": "NetBridge"}), timeout=timeout) as r:
            raw = r.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (OSError, urllib.error.URLError) as e:
        return False, str(e)[:120]
    try:
        return bool(json.loads(raw).get("ok")), raw.strip()[:120]
    except ValueError:
        return False, raw.strip()[:120] or "empty answer"
