import base64, urllib.request
from app.utils.parser import parse_many

MAX_BYTES = 10 * 1024 * 1024


def fetch_subscription(url, proxy=None, timeout=20):
    """Download a subscription link and return (profiles, errors).
    proxy: e.g. 'http://127.0.0.1:10809' if the site needs the tunnel."""
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url.strip(), headers={"User-Agent": "NetBridge"})
    r = opener.open(req, timeout=timeout)
    try:
        raw = r.read(MAX_BYTES + 1)
    finally:
        getattr(r, "close", lambda: None)()
    if len(raw) > MAX_BYTES:
        raise ValueError("subscription is larger than 10 MB - refused")
    raw = raw.decode("utf-8", errors="replace").strip()
    if "://" not in raw:                      # most subscriptions are base64 (maybe wrapped over several lines)
        try:
            b = "".join(raw.split())
            b += "=" * (-len(b) % 4)
            raw = base64.b64decode(b.replace("-", "+").replace("_", "/")).decode("utf-8", errors="replace")
        except Exception:
            pass
    return parse_many(raw)
