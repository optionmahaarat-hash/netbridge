import time, urllib.request

def real_delay(proxy="http://127.0.0.1:10809", url="http://www.gstatic.com/generate_204", timeout=8):
    """Real test through the running tunnel. Returns ms or raises."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    t = time.time()
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "NetBridge"}), timeout=timeout) as r:
        r.read(16)
    return int((time.time() - t) * 1000)


def exit_info(proxy="http://127.0.0.1:10809", timeout=10):
    """What the outside world sees when you use the tunnel: IP, country, ISP."""
    import json
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    url = "http://ip-api.com/json/?fields=query,country,countryCode,isp,org"
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "NetBridge"}), timeout=timeout) as r:
        return json.loads(r.read())


# ---- site check: what the browser really needs (HTTPS CONNECT + a real page body), not just one tiny HTTP 204
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
SITES = [   # (label, url, accepted status test)
    ("YouTube", "https://www.youtube.com/generate_204", lambda c: c == 204),
    ("Instagram", "https://www.instagram.com/", lambda c: 200 <= c < 400),
    ("Google", "https://www.google.com/generate_204", lambda c: c == 204),
]


def _fetch(proxy, url, timeout, read=20000):
    """(status, ms) through the proxy; reads up to `read` bytes so a stalled body is noticed."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    t = time.time()
    with opener.open(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"}), timeout=timeout) as r:
        r.read(read)
        status = r.status
    return status, int((time.time() - t) * 1000)


def check_sites(proxy, timeout=10, sites=None, fetch=_fetch):
    """Runs all checks in parallel (a browser opens many connections at once).
    Returns [(label, ok, ms, detail)]."""
    from concurrent.futures import ThreadPoolExecutor
    sites = sites or SITES
    if not sites:
        return []

    def one(site):
        label, url, accept = site
        try:
            code, ms = fetch(proxy, url, timeout)
            return label, bool(accept(code)), ms, f"HTTP {code}"
        except Exception as e:
            code = getattr(e, "code", None)            # HTTPError: the server answered with an error status
            if code is not None and accept(code):
                return label, True, 0, f"HTTP {code}"
            return label, False, -1, (f"HTTP {code}" if code else str(e)[:80])
    with ThreadPoolExecutor(max_workers=len(sites)) as ex:
        return list(ex.map(one, sites))


def sites_ok(results):
    return all(ok for _, ok, _, _ in results)


def sites_ms(results):
    ms = [m for _, ok, m, _ in results if ok and m > 0]
    return int(sum(ms) / len(ms)) if ms else 1


# ---- upload check: some channels pass small downloads but stall after ~6 upstream packets (PattNG report).
# A page that needs a request body (login, form, any POST) then hangs. A 16-byte GET never notices.
UPLOAD_URL = "https://speed.cloudflare.com/__up"
# A second, unrelated host: if one is slow or blocked it must not make every profile look upload-limited.
UPLOAD_URLS = (UPLOAD_URL, "https://www.google.com/gen_204")
UPLOAD_BYTES = 50_000


def _post(proxy, url, timeout, size=UPLOAD_BYTES):
    """POST `size` bytes through the proxy. Returns ms once the server has answered (any HTTP status counts:
    the body got through). Raises on stall/timeout/connection errors."""
    import urllib.error
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    req = urllib.request.Request(url, data=b"\0" * size, method="POST",
                                 headers={"User-Agent": UA, "Content-Type": "application/octet-stream"})
    t = time.time()
    try:
        with opener.open(req, timeout=timeout) as r:
            r.read(64)
    except urllib.error.HTTPError:
        pass
    return int((time.time() - t) * 1000)


def check_upload(proxy, timeout=10, url=None, size=UPLOAD_BYTES, post=_post):
    """(ok, ms, detail). ok=False means the upload stalled or failed: the profile is 'upload-limited'."""
    err = "no url"
    for u in ((url,) if url else UPLOAD_URLS):
        try:
            ms = post(proxy, u, timeout, size)
            return True, ms, f"uploaded {size // 1000} KB"
        except Exception as e:
            err = str(e)[:80] or type(e).__name__
    return False, -1, err
