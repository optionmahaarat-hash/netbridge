"""Logic of NetBridge Lite without any UI (so it can be tested)."""
import itertools, json, re, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from app.core import autobypass, tlsup
from app.core.delay_all import test_many, test_one
from app.storage.atomic import read_json, write_json_atomic
from app.storage.profiles import load_profiles, save_profiles
from app.utils.parser import parse_many
from app.utils.subscription import fetch_subscription
from app.utils.validator import validate_profile

SETTINGS = Path("data/lite_settings.json")
DEFAULTS = {"lang": "fa", "iran_direct": True, "system_proxy": True, "selected": "auto",
            "subs": [], "update_urls": [], "last_update_check": 0, "last_version": ""}
# "Works" must mean HTTPS works: a server that only passes plain HTTP shows "connected" but real sites stay blank.
PROBE_URL = "https://www.gstatic.com/generate_204"
TLS_PORT0 = 23100
LINK_RE = re.compile(r"(vless|vmess|trojan|ss|hysteria2|hy2)://", re.I)


def load_settings():
    s = json.loads(json.dumps(DEFAULTS))
    data = read_json(SETTINGS, {})
    if isinstance(data, dict):
        s.update(data)
    for k in ("subs", "update_urls"):               # a hand-edited / damaged file must not crash the UI later
        if not isinstance(s.get(k), list):
            s[k] = []
    return s


def save_settings(s):
    write_json_atomic(SETTINGS, s)


def seed_profiles(data_file, seed_file):
    """First run only: when there is no server list yet, start with the servers bundled in the installer.
    Never touches an existing list (even an empty one), so the user's own changes are never overwritten."""
    data_file, seed_file = Path(data_file), Path(seed_file)
    if data_file.exists() or not seed_file.exists():
        return 0
    seed = read_json(seed_file, [])
    seed = [p for p in seed if isinstance(p, dict) and not validate_profile(p)] if isinstance(seed, list) else []
    if seed:
        write_json_atomic(data_file, seed)
    return len(seed)


def profile_key(p):
    return "|".join(str(p.get(k, "")) for k in ("type", "server", "port", "uuid", "password"))


def classify_text(text):
    """'links' | 'json' | 'subscription' | None  - what did the user copy?"""
    t = (text or "").strip()
    if not t or len(t) > 3_000_000:
        return None
    if LINK_RE.search(t):
        return "links"
    if t[:1] in "{[" and '"outbounds"' in t:
        return "json"
    if re.fullmatch(r"https?://\S+", t):
        return "subscription"
    return None


def merge(profiles, new, group=None):
    """Adds valid, non-duplicate profiles in place. Returns (added, duplicates, invalid)."""
    seen = {profile_key(p) for p in profiles}
    added = dup = bad = 0
    for p in new:
        if validate_profile(p):
            bad += 1; continue
        k = profile_key(p)
        if k in seen:
            dup += 1; continue
        seen.add(k)
        if group: p["group"] = group
        profiles.append(p); added += 1
    return added, dup, bad


def add_text(profiles, text):
    """Links / sing-box JSON -> profiles. Returns (added, dup, bad, parse_errors)."""
    found, errors = parse_many(text)
    return (*merge(profiles, found), errors)


def add_subscription(profiles, url, settings, proxy=None):
    found, errors = fetch_subscription(url, proxy=proxy)
    group = urlparse(url.strip()).hostname or "subscription"
    r = merge(profiles, found, group)
    if not any(s["url"] == url.strip() for s in settings["subs"]):
        settings["subs"].append({"url": url.strip(), "group": group})
    return (*r, errors)


def refresh_subscriptions(profiles, settings, proxy=None):
    """Re-downloads every saved subscription: its group is replaced by the fresh list (old delays kept)."""
    total, failed = 0, []
    for s in settings["subs"]:
        try:
            found, _ = fetch_subscription(s["url"], proxy=proxy)
        except Exception as e:
            failed.append((s["url"], str(e))); continue
        if not [p for p in found if not validate_profile(p)]:
            # an empty / error page must NOT delete the servers we already have
            failed.append((s["url"], "no valid servers in the downloaded list - kept the old ones")); continue
        old = {profile_key(p): p for p in profiles if p.get("group") == s["group"]}
        profiles[:] = [p for p in profiles if p.get("group") != s["group"]]
        fresh = [p for p in found if not validate_profile(p)]
        for p in fresh:
            p["group"] = s["group"]
            o = old.get(profile_key(p))
            if o:
                for k in ("delay", "delay_ts", "pcs"):
                    if k in o: p.setdefault(k, o[k])
        profiles.extend(fresh)
        total += len(fresh)
    return total, failed


def _rank(p):
    d = p.get("delay")
    if d is None: return (1, 0)          # never tested
    if d < 0: return (2, 0)              # failed last time
    return (0, d)                        # known good, fastest first


def find_fastest(exe, profiles, want=4, max_total=60, batch=12, on_progress=None, cancelled=lambda: False):
    """Tests profiles in batches (known-good first) until `want` work. Returns [(profile, ms)] fastest first."""
    order = sorted(profiles, key=_rank)[:max_total]
    ok, done = [], 0
    for i in range(0, len(order), batch):
        if cancelled() or len(ok) >= want:
            break
        chunk = order[i:i + batch]

        def got(p, ms):
            nonlocal done
            p["delay"], p["delay_ts"] = ms, int(time.time())
            done += 1
            if ms >= 0: ok.append((p, ms))
            if on_progress: on_progress(done, len(order))

        test_many(exe, [(p, p) for p in chunk], got, workers=len(chunk), cancelled=cancelled, url=PROBE_URL)
    return sorted(ok, key=lambda x: x[1])


def auto_find(exe, profiles, on_status=None, on_progress=None, cancelled=lambda: False, want=4, runner=None):
    """The full AUTO search of the main app (every server x every bypass method, strict YouTube/Instagram check,
    clean-IP scan, fallbacks). The winning method is written into each winning profile.
    Returns ([(profile, ms)] fastest first - encrypted ones preferred, summary dict)."""
    runner = runner or autobypass.auto_run
    wins, lock = [], threading.Lock()

    def on_win(p, v, ms):
        with lock:
            autobypass.apply_variant(p, v)
            p["delay"], p["delay_ts"] = ms, int(time.time())
            wins.append((p, ms))

    kw = {}
    if on_status: kw["on_status"] = on_status
    if on_progress: kw["on_progress"] = on_progress
    res = runner(exe, profiles, on_win, cancelled=cancelled, want=want, **kw)
    pool = [w for w in wins if autobypass.is_tls(w[0])] or wins
    return sorted(pool, key=lambda x: x[1]), res


def choose_connection(ok, k=4):
    """(profiles, mode): several working servers -> Xray balancer with fail-over, one -> plain."""
    pool = [p for p, _ in ok][:k]
    return pool, ("auto" if len(pool) > 1 else "manual")


def pin_pending(profiles, fetch):
    """Pins self-signed servers (Xray 26.7 removed allowInsecure). fetch(profile)->sha256. Returns pinned count."""
    n = 0
    for p in profiles:
        if p.get("insecure") and not p.get("pcs") and not p.get("pin_failed"):
            try:
                p["pcs"] = fetch(p); n += 1
            except Exception:
                p["pin_failed"] = True
    return n


def plain_profiles(profiles, force=False):
    return [p for p in profiles if tlsup.is_plain(p) and (force or not p.get("tls_tried"))]


def upgrade_plain(exe, profiles, on_progress=None, cancelled=lambda: False, cap=24, workers=6, force=False,
                  handshake_fn=None):
    """For servers exported WITHOUT TLS (e.g. Cloudflare configs on port 80), look for a TLS port on the same host
    (same port, 443, 8443, 2053, 2083, 2087, 2096). A candidate counts only if it answers a TLS handshake AND carries
    real HTTPS traffic. A server that has no TLS at all cannot be converted - that is reported, never faked.
    Returns [(original, new_profile, info)]."""
    todo = plain_profiles(profiles, force)[:cap]
    ports, lock, results, done = itertools.count(TLS_PORT0), threading.Lock(), [], [0]
    kw = {"handshake_fn": handshake_fn} if handshake_fn else {}

    def works(q):
        if cancelled(): return None
        ms = test_one(exe, q, next(ports), url=PROBE_URL)
        return {"ms": ms} if ms >= 0 else None

    def job(p):
        if cancelled(): return
        try:
            q, info = tlsup.find_tls(p, works, **kw)
        except Exception:
            q, info = None, None
        with lock:
            p["tls_tried"] = True
            if q: results.append((p, q, info))
            done[0] += 1
            if on_progress: on_progress(done[0], len(todo))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(job, todo))
    return results


def apply_upgrade(profiles, results):
    """Same port -> the profile is fixed in place; another TLS port -> added as a new profile (original kept)."""
    n = 0
    for p, q, info in results:
        q["delay"], q["delay_ts"] = (info or {}).get("ms"), int(time.time())
        idx = next((i for i, x in enumerate(profiles) if x is p), None)
        if int(q["port"]) == int(p["port"]) and idx is not None:
            profiles[idx] = q; n += 1
        else:
            n += merge(profiles, [q], q.get("group"))[0]
    return n
