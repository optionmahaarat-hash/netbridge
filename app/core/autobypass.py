"""Auto bypass: find, for every profile, the bypass method that actually works on YOUR network.

Instead of trying Off / PattNG / Standard / ECH by hand, each profile is tested in a private Xray
(real HTTP request through it) with every method in turn; the first one that answers wins and is
written into the profile. ECH is only tried with a DNS-over-HTTPS server that is reachable from
here (the ECH keys must be downloaded before the connection can start - this is what failed with
1.1.1.1 on a network that blocks it).

Phases (each one only runs if the previous gave no working TLS profile):
  1. every TLS profile x every method
  2. scan clean Cloudflare IPs and retry the TLS profiles with the best ones
  3. last resort: plain (non-TLS) profiles - they work but are NOT encrypted, the caller is told
"""
import base64
import socket
import ssl
import struct
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from app.core import bypass, ipscan
from app.core.delay_all import test_one
from app.utils import latency

BASE_PORT = 22000
ECH_PUBLIC_NAME = "cloudflare-ech.com"
DOH_CANDIDATES = [
    "https://dns.google/dns-query",
    "https://1.1.1.1/dns-query",
    "https://cloudflare-dns.com/dns-query",
    "https://8.8.8.8/dns-query",
    "https://dns.quad9.net/dns-query",
    "https://9.9.9.9/dns-query",
]


# ------------------------------------------------------------------ helpers
def is_tls(p):
    return str(p.get("security", "")).lower() == "tls"


def _dns_query(name, qtype=65):
    q = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
    for part in name.split("."):
        q += bytes([len(part)]) + part.encode()
    return q + b"\x00" + struct.pack(">HH", qtype, 1)


def doh_works(url, timeout=4.0):
    """True if a real DoH query for the ECH public name is answered from this machine (no proxy)."""
    try:
        dns = base64.urlsafe_b64encode(_dns_query(ECH_PUBLIC_NAME)).decode().rstrip("=")
        req = urllib.request.Request(f"{url}?dns={dns}", headers={
            "Accept": "application/dns-message", "User-Agent": "NetBridge"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never through our own proxy
        with opener.open(req, timeout=timeout) as r:
            return r.status == 200 and len(r.read(512)) > 12
    except Exception:
        return False


def reachable_doh(candidates=None, timeout=4.0, workers=6):
    cands = list(candidates or DOH_CANDIDATES)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        ok = list(ex.map(lambda u: doh_works(u, timeout), cands))
    return [u for u, good in zip(cands, ok) if good]


_V6 = {}


def is_name(host):
    """True for a server given by name (not an IPv4 / IPv6 literal)."""
    host = str(host or "")
    return bool(host) and ":" not in host and not host.replace(".", "").isdigit()


def resolve6(host, port=443):
    """First IPv6 address of a server name (cached, None if it has none). A server that is already an IP is not resolved."""
    host = str(host or "")
    if not is_name(host):
        return None
    if host not in _V6:
        ip = None
        try:
            for *_x, sa in socket.getaddrinfo(host, int(port or 443), socket.AF_INET6, socket.SOCK_STREAM):
                ip = sa[0]
                break
        except Exception:
            ip = None
        _V6[host] = ip
    return _V6[host]


def variants(profile, doh_urls=(), clean_ip=None, ipv6=False):
    """Ordered list of override dicts to try for one profile.
    ipv6=True adds, at the END, IPv6 entry points for servers given by name ({"ip6": True} = connect to the server's AAAA address)."""
    if not is_tls(profile):
        return [{"bypass": "off"}]
    # "off", then every preset the (updatable) presets file marks for AUTO: pattng, standard and any new ones
    out = [{"bypass": "off"}] + [{"bypass": n} for n in bypass.auto_names()]
    for u in list(doh_urls)[:2]:
        out.append({"bypass": "ech", "ech": f"{ECH_PUBLIC_NAME}+{u}"})
    if clean_ip:
        out = [dict(v, address_override=clean_ip) for v in out]
    elif ipv6 and not profile.get("address_override") and is_name(profile.get("server")):
        # the name is resolved later, inside the worker thread (find_variant skips the variant when there is no AAAA record)
        first = (bypass.auto_names() or ["off"])[0]
        out += [{"bypass": "off", "ip6": True}] + ([{"bypass": first, "ip6": True}] if first != "off" else [])
    return out


def _with(profile, v):
    p = dict(profile)
    p.pop("ech", None)
    v = dict(v)
    if v.pop("ip6", False):
        ip = resolve6(profile.get("server"), profile.get("port"))
        if ip:
            v["address_override"] = ip
    p.update(v)
    return p


def apply_variant(profile, v):
    """Write a winning variant into the real profile (keeps chain, custom fm/cs, etc.)."""
    profile["bypass"] = v.get("bypass", "off")
    if v.get("ech"):
        profile["ech"] = v["ech"]
    else:
        profile.pop("ech", None)
    if v.get("address_override"):
        profile["address_override"] = v["address_override"]
    elif v.get("ip6"):
        ip = resolve6(profile.get("server"), profile.get("port"))
        if ip:
            profile["address_override"] = ip


def label(v):
    s = v.get("bypass", "off")
    if v.get("ech"):
        s += " via " + v["ech"].split("+", 1)[-1]
    if v.get("address_override"):
        s += f" @ {v['address_override']}"
    if v.get("ip6"):
        s += " (IPv6)"
    return s


# ------------------------------------------------------------------ strict verification
UPLOAD_LIMITED = {"n": 0}                     # profiles that opened the sites but stalled on a 50 KB upload
_ULOCK = threading.Lock()


def _verify(port, timeout=10, upload=None):
    """Real HTTPS requests to YouTube / Instagram / Google through the test tunnel, then a 50 KB upload
    (catches the ~6-packet upload limit). ms or None."""
    proxy = f"http://127.0.0.1:{port}"
    res = latency.check_sites(proxy, timeout=timeout)
    if not latency.sites_ok(res):
        return None
    ok, _, _ = (upload or latency.check_upload)(proxy, timeout)
    if not ok:
        with _ULOCK:
            UPLOAD_LIMITED["n"] += 1
        return None
    return latency.sites_ms(res)


def strict_test(executable, profile, port, timeout=6):
    """Passes only if the profile also opens the sites that matter (not just a 16-byte generate_204)."""
    return test_one(executable, profile, port, timeout=timeout, verify=_verify)


# ------------------------------------------------------------------ engine
def find_variant(executable, profile, port, vs, cancelled=lambda: False, timeout=6, tester=strict_test):
    """First (variant, ms) that works, or None."""
    for v in vs:
        if cancelled():
            return None
        if v.get("ip6") and not resolve6(profile.get("server"), profile.get("port")):
            continue                                   # no AAAA record: nothing to test
        ms = tester(executable, _with(profile, v), port, timeout=timeout)
        if ms is not None and ms >= 0:
            return v, ms
    return None


RACE_BASE = 23000
RACE_WIDTH = 3                                          # clean IPs tested at the same time for one profile


def find_variant_race(executable, profile, port, groups, cancelled=lambda: False, timeout=6, tester=strict_test):
    """groups: list of lists of variants. A group holds the SAME method on different clean IPs.
    Groups are tried in order (method order is kept); inside a group all IPs run at the same time and the
    fastest working one wins. Returns (variant, ms) or None."""
    slot = (port - BASE_PORT) * RACE_WIDTH
    for g in groups:
        if cancelled():
            return None
        g = g[:RACE_WIDTH]
        with ThreadPoolExecutor(max_workers=len(g)) as ex:
            res = list(ex.map(lambda kv: (kv[1], tester(executable, _with(profile, kv[1]), RACE_BASE + slot + kv[0],
                                                       timeout=timeout)), enumerate(g)))
        ok = [(ms, v) for v, ms in res if ms is not None and ms >= 0]
        if ok:
            ms, v = min(ok, key=lambda t: t[0])
            return v, ms
    return None


_LOCK = threading.Lock()


def _run_phase(executable, jobs, on_win, cancelled, want, state, workers, tester, key="tls_wins", finder=find_variant):
    """jobs: list of (profile, variants). Stops early once `want` winners (state[key]) exist."""
    def stop():
        return cancelled() or state[key] >= want

    def job(n_item):
        n, (p, vs) = n_item
        if stop():
            return
        r = finder(executable, p, BASE_PORT + n, vs, cancelled=stop, tester=tester)
        with _LOCK:
            if r:
                if is_tls(p):
                    state["tls_wins"] += 1
                state["wins"] += 1
            state["done"] += 1
            done, total = state["done"], state["total"]
        if r:
            on_win(p, r[0], r[1])
        state["progress"](done, total)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(job, enumerate(jobs)))


def auto_run(executable, profiles, on_win, on_status=lambda s: None, on_progress=lambda d, t: None,
             cancelled=lambda: False, want=4, workers=10, tester=strict_test, doh_check=reachable_doh,
             scanner=ipscan, relaxed_tester=test_one):
    """Tries to find `want` working TLS profiles. on_win(profile, variant, ms) is called for each success.
    Returns {"tls": n, "plain": n, "insecure_fallback": bool}."""
    UPLOAD_LIMITED["n"] = 0
    profiles = [p for p in profiles if p.get("engine") not in ("aether", "gscript")]          # the local WARP / Google Script entries is not a server to search
    tls = [p for p in profiles if is_tls(p)]
    plain = [p for p in profiles if not is_tls(p)]
    # profiles that worked before go first
    tls.sort(key=lambda p: (p.get("delay", 10 ** 6) if p.get("delay", -1) >= 0 else 10 ** 7))

    on_status("Checking which DNS-over-HTTPS servers are reachable (for ECH)...")
    doh = doh_check() if tls else []
    on_status("ECH DoH reachable: " + (", ".join(doh) if doh else "none - ECH will be skipped"))

    has6 = getattr(scanner, "has_ipv6", None)
    v6 = bool(has6()) if (tls and callable(has6)) else False
    if tls:
        on_status("IPv6: " + ("route available - IPv6 entry points are tried last" if v6 else "no IPv6 route here - skipped"))

    state = {"tls_wins": 0, "wins": 0, "done": 0, "total": len(tls), "progress": on_progress}
    if tls:
        on_status(f"Phase 1: {len(tls)} TLS profile(s) x methods (stops after {want} working)")
        _run_phase(executable, [(p, variants(p, doh, ipv6=v6)) for p in tls], on_win, cancelled, want, state, workers, tester)

    if state["tls_wins"] == 0 and tls and not cancelled():
        cf = [p for p in tls if scanner.looks_cloudflare(p)]
        if cf:
            on_status("Phase 2: no TLS profile worked - scanning clean Cloudflare IPs...")
            port, sni = scanner.scan_target(cf[0])
            found = []
            ranges = scanner.load_ranges()
            if v6 and callable(getattr(scanner, "load_ranges6", None)):
                ranges = ranges + scanner.load_ranges6()
            scanner.scan(scanner.sample_ips(ranges, 300), port, sni,
                         lambda ip, ms, colo: found.append((ms, ip)), cancelled=cancelled)
            ips = [ip for _, ip in sorted(found)[:3]]
            on_status(f"Clean IPs found: {', '.join(ips) if ips else 'none'}" +
                      (f" - racing the best {min(len(ips), RACE_WIDTH)} per method" if len(ips) > 1 else ""))
            if ips:
                # race: for every profile, each method is tried on all the clean IPs at once; the fastest IP wins
                jobs = []
                for p in cf[:20]:
                    lists = [variants(p, doh, clean_ip=ip) for ip in ips[:RACE_WIDTH]]
                    jobs.append((p, [list(g) for g in zip(*lists)]))
                state.update(done=0, total=len(jobs))
                _run_phase(executable, jobs, on_win, cancelled, want, state, max(2, workers // RACE_WIDTH), tester,
                           finder=find_variant_race)

    insecure = False
    if state["tls_wins"] == 0 and plain and not cancelled():
        on_status("Phase 3: no TLS profile worked - trying plain profiles (NOT encrypted)")
        state.update(done=0, total=min(len(plain), 40))
        before = state["wins"]
        _run_phase(executable, [(p, [{"bypass": "off"}]) for p in plain[:40]], on_win, cancelled, 3, state, workers, tester,
                   key="wins")
        insecure = state["wins"] > before
    relaxed = False
    if UPLOAD_LIMITED["n"]:
        on_status(f"Upload test: {UPLOAD_LIMITED['n']} attempt(s) opened the sites but stalled on a 50 KB upload "
                  "(upload-limited channel, e.g. the ~6-packet limit) - rejected")
    if state["wins"] == 0 and tls and not cancelled() and relaxed_tester is not None and relaxed_tester is not tester:
        # Nothing opened YouTube/Instagram. Fall back to the old basic test so the user is not left with nothing,
        # but say so: these profiles may connect without opening those sites.
        on_status("No profile passed the YouTube/Instagram + upload check - falling back to the basic test (weaker; "
                  "these may connect but stall on uploads)")
        state.update(done=0, total=len(tls))
        _run_phase(executable, [(p, variants(p, doh, ipv6=v6)) for p in tls], on_win, cancelled, 2, state, workers, relaxed_tester)
        relaxed = state["wins"] > 0
    return {"tls": state["tls_wins"], "plain": state["wins"] - state["tls_wins"],
            "insecure_fallback": insecure, "relaxed_fallback": relaxed}
