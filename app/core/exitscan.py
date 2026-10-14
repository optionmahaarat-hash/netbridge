"""Exit scan: what do websites see when you use each profile?

For every profile we start a private Xray, ask a geo service through it, and report country / ISP /
datacenter / Cloudflare. Use it to find a NON-Cloudflare exit in a country a service supports
(e.g. for Gemini / NotebookLM) among many free profiles.
"""
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core.config_generator import write_config
from app.core.delay_all import _wait_port, NOWIN
from app.utils.leakcheck import SOURCES, _get

BASE_PORT = 22000
ORDER = ["ip-api", "ipwho.is", "ipinfo"]       # first one that answers wins (free services have rate limits)


# Pages that Google redirects to a "not available here" page when it does not like your exit IP.
GOOGLE_CHECKS = {"NotebookLM": "https://notebooklm.google.com/",
                 "Gemini": "https://gemini.google.com/app",
                 "AI Studio": "https://aistudio.google.com/"}
BLOCK_URL_MARKS = ("location=unsupported", "unsupported-country", "/unavailable", "not-available")
BLOCK_TEXT_MARKS = ("not available in your country", "isn't available in your country",
                    "isn't supported in your country", "not supported in your country",
                    "not available in your region")


def check_site(url, proxy=None, timeout=12):
    """'ok' (no block seen) | 'blocked' | 'timeout' | 'tls-error' | 'error'. Follows redirects and looks at the final URL and page text.
    Heuristic: a block that is drawn only by JavaScript is not seen here."""
    h = urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {})
    op = urllib.request.build_opener(h)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                                               "Accept-Language": "en-US,en;q=0.9"})
    try:
        resp = op.open(req, timeout=timeout)
        final, body = resp.geturl().lower(), resp.read(300_000).decode("utf-8", "replace").lower()
    except urllib.error.HTTPError as e:
        final, body = (e.url or "").lower(), ""
    except Exception as e:
        why = getattr(e, "reason", e)
        if isinstance(e, TimeoutError) or isinstance(why, TimeoutError) or "timed out" in str(why).lower():
            return "timeout"
        if isinstance(why, ssl.SSLError) or isinstance(e, ssl.SSLError):
            return "tls-error"
        return "error"
    if any(m in final for m in BLOCK_URL_MARKS) or any(m in body for m in BLOCK_TEXT_MARKS):
        return "blocked"
    return "ok"


def is_workers(profile):
    """*.workers.dev / *.pages.dev profiles always exit through Cloudflare."""
    for k in ("sni", "host", "server"):
        v = (profile.get(k) or "").lower()
        if v.endswith(".workers.dev") or v.endswith(".pages.dev"):
            return True
    return False


def is_cloudflare(info):
    return "cloudflare" in ((info or {}).get("org") or "").lower()


def probe_exit(executable, profile, port, timeout=10, sources=None, checks=None):
    """Returns {ip, cc, org, hosting, proxy, cloudflare, ms} through this profile, or None."""
    tmp = Path(tempfile.mkdtemp(prefix="nbexit_"))
    cfg = tmp / "t.json"
    proc = None
    try:
        write_config(profile, cfg, {"routing": {"lan": False}}, socks_port=0, http_port=port, loglevel="none")
        proc = subprocess.Popen([str(executable), "run", "-c", str(cfg)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NOWIN)
        if not _wait_port(port, proc=proc):
            return None
        proxy = f"http://127.0.0.1:{port}"
        for name in (sources or ORDER):
            url, parse = SOURCES[name] if isinstance(name, str) else name
            try:
                t0 = time.perf_counter()
                r = parse(_get(url, proxy, timeout))
                r["ms"] = int((time.perf_counter() - t0) * 1000)
                r["cloudflare"] = is_cloudflare(r)
                if checks:
                    r["checks"] = {n: check_site(u, proxy) for n, u in checks.items()}
                return r
            except Exception:
                continue
        return None
    except Exception:
        return None
    finally:
        if proc:
            proc.terminate()
            try: proc.wait(timeout=2)
            except Exception: proc.kill()
        try:
            cfg.unlink(missing_ok=True); tmp.rmdir()
        except Exception:
            pass


def scan_many(executable, items, on_result, workers=8, cancelled=lambda: False, **kw):
    """items: list of (key, profile). on_result(key, info_or_None) as each finishes."""
    def job(n_item):
        n, (key, prof) = n_item
        if cancelled():
            return
        on_result(key, probe_exit(executable, prof, BASE_PORT + n, **kw))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(job, enumerate(items)))


def describe(info):
    if not info:
        return "no answer (dead profile or blocked)"
    tags = []
    if info.get("cloudflare"): tags.append("CLOUDFLARE")
    if info.get("hosting"): tags.append("datacenter")
    if info.get("proxy"): tags.append("vpn-list")
    word = {"ok": "OK", "blocked": "BLOCKED", "timeout": "TIMEOUT", "tls-error": "TLS-ERR", "error": "ERR"}
    chk = "  ".join(f"{n}:{word.get(v, '?')}" for n, v in (info.get("checks") or {}).items())
    return f"{info.get('cc') or '??'}   {info.get('ip')}   {(info.get('org') or '')[:30]}   {' '.join(tags)}   {chk}".rstrip()
