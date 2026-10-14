"""Full exit check: what do websites really see when you are connected?

Why: 'location unsupported' can come from
  1. the exit IP being placed in the wrong country by ONE geo database (sites use different ones),
  2. the exit IP being a datacenter / known VPN address,
  3. traffic that does not go through the tunnel at all,
  4. signals that are not the IP: WebRTC, time zone, language (Persian), browser location.
This module checks 1-3 over the tunnel and reports 4 from the local machine.
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PROXY = "http://127.0.0.1:10809"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NetBridge"


def _get(url, proxy, timeout):
    h = urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {})
    op = urllib.request.build_opener(h)
    return op.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout).read().decode("utf-8", "replace")


# ---- one parser per service: text -> {"ip", "cc", optional "tz", "org", "hosting", "proxy"}
def _p_ipapi(t):
    d = json.loads(t)
    if d.get("status") != "success":
        raise ValueError(d.get("message", "fail"))
    return {"ip": d["query"], "cc": d.get("countryCode"), "tz": d.get("timezone"),
            "org": d.get("org") or d.get("isp"), "hosting": d.get("hosting"), "proxy": d.get("proxy")}

def _p_ipwho(t):
    d = json.loads(t)
    if d.get("success") is False:
        raise ValueError(d.get("message", "fail"))
    return {"ip": d["ip"], "cc": d.get("country_code"), "tz": (d.get("timezone") or {}).get("id"),
            "org": (d.get("connection") or {}).get("org")}

def _p_ipinfo(t):
    d = json.loads(t)
    return {"ip": d["ip"], "cc": d.get("country"), "tz": d.get("timezone"), "org": d.get("org")}

def _p_cf(t):
    d = dict(line.split("=", 1) for line in t.splitlines() if "=" in line)
    return {"ip": d["ip"], "cc": d.get("loc"), "org": "Cloudflare edge " + d.get("colo", "?")}

def _p_countryis(t):
    d = json.loads(t)
    return {"ip": d["ip"], "cc": d.get("country")}

SOURCES = {
    "ip-api": ("http://ip-api.com/json/?fields=status,message,query,countryCode,timezone,isp,org,proxy,hosting", _p_ipapi),
    "ipwho.is": ("https://ipwho.is/", _p_ipwho),
    "ipinfo": ("https://ipinfo.io/json", _p_ipinfo),
    "Cloudflare": ("https://www.cloudflare.com/cdn-cgi/trace", _p_cf),
    "country.is": ("https://api.country.is/", _p_countryis),
}


def query_all(proxy=PROXY, timeout=8):
    """Ask every service through the tunnel, in parallel. Returns {name: result-or-None}."""
    def one(item):
        name, (url, parse) = item
        try:
            return name, parse(_get(url, proxy, timeout))
        except Exception:
            return name, None
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as ex:
        return dict(ex.map(one, SOURCES.items()))


def direct_ip(timeout=6):
    """Your IP WITHOUT the tunnel (None if it cannot be read)."""
    try:
        return _p_cf(_get(SOURCES["Cloudflare"][0], None, timeout))
    except Exception:
        return None


def local_info():
    """Signals the browser/OS leaks that are not the IP."""
    d = {"utc_offset_min": time.localtime().tm_gmtoff // 60, "locale": ""}
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(85)
        ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85)
        d["locale"] = buf.value
    except Exception:
        try:
            import locale
            d["locale"] = locale.getlocale()[0] or ""
        except Exception:
            pass
    return d


def _tz_offset_min(tzid):
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return int(ZoneInfo(tzid).utcoffset(datetime.now()).total_seconds() // 60)
    except Exception:
        return None


def analyze(res, local=None, direct=None):
    """res: {name: result|None}. Returns a list of (level, text); level = ok | warn | bad | info."""
    out = []
    good = {n: r for n, r in res.items() if r and r.get("cc")}
    if not good:
        return [("bad", "No geo service answered through the tunnel. Is NetBridge connected? "
                        "(Check the HTTP proxy 127.0.0.1:10809 and the log.)")]
    for n, r in good.items():
        extra = f" - {r['org']}" if r.get("org") else ""
        out.append(("info", f"{n}: {r['ip']}  {r['cc']}{extra}"))

    ccs = {r["cc"].upper() for r in good.values()}
    if "IR" in ccs:
        who = ", ".join(n for n, r in good.items() if r["cc"].upper() == "IR")
        out.append(("bad", f"{who} still say the exit is IRAN. Sites that use that database will reject you. "
                           "Pick another server (a different IP), or send that site through another exit "
                           "(Routing -> Sites that reject Iranian IPs)."))
    elif len(ccs) > 1:
        out.append(("warn", "The geo databases DISAGREE about your exit IP (" + ", ".join(sorted(ccs)) + "). "
                            "A site that uses the wrong one will say 'unsupported location'. Try another server / IP."))
    else:
        out.append(("ok", f"All {len(good)} services agree: the exit country is {next(iter(ccs))}."))

    ips = {r["ip"] for r in good.values()}
    cf = any("cloudflare" in (r.get("org") or "").lower() and not (r.get("org") or "").startswith("Cloudflare edge")
             for r in good.values())
    if cf:
        out.append(("bad", "The exit is CLOUDFLARE (WARP / Workers / Pages), not a real server of yours. Its IPs are "
                           "shared, change all the time, and are on VPN/proxy lists, so many sites (AI, banking, "
                           "streaming) answer 'unsupported location' even though the country is right. "
                           "Changing between Cloudflare profiles will NOT help: use a non-Cloudflare server "
                           "(your own VPS, e.g. VLESS+Reality) for those sites: Routing -> Sites that reject "
                           "Iranian IPs -> pick that server."))
    elif len(ips) > 1:
        out.append(("warn", "Different services saw different IPs: " + ", ".join(sorted(ips)) +
                            ". Auto/balancer mode or a rotating exit; different sites may see different IPs. "
                            "Use Manual mode for sensitive sites."))
    if direct and direct.get("ip") in ips:
        out.append(("bad", "Your REAL IP equals the exit IP: this test did not go through a tunnel."))

    api = good.get("ip-api") or {}
    if api.get("hosting"):
        out.append(("warn", "The exit IP is a DATACENTER address. Many services (AI, banking, streaming) treat that "
                            "as unsupported even if the country is right. A different server / provider may work."))
    if api.get("proxy") and not cf:
        out.append(("warn", "The exit IP is on a known VPN/proxy list."))

    if local:
        tz = next((r["tz"] for r in good.values() if r.get("tz")), None)
        exit_off = _tz_offset_min(tz) if tz else None
        if exit_off is not None and exit_off != local.get("utc_offset_min"):
            out.append(("warn", f"Windows time zone (UTC{local['utc_offset_min']/60:+g}) does not match the exit "
                                f"({tz}, UTC{exit_off/60:+g}). Some sites read the browser time zone. "
                                "Change the Windows time zone to match, or accept this risk."))
        loc = (local.get("locale") or "").lower()
        if loc.startswith("fa") or loc.endswith("-ir") or loc.endswith("_ir"):
            out.append(("warn", "Windows language/region is Persian/Iran. Browsers send Accept-Language: fa and "
                                "websites can use it. Use the 'Open clean browser' button (it sends en-US)."))
    out.append(("info", "Not testable here: WebRTC and browser Location permission. "
                        "'Open clean browser' disables WebRTC leaks; deny Location for the site."))
    return out


ICON = {"ok": "[OK]  ", "warn": "[!]   ", "bad": "[X]   ", "info": "      "}

def format_report(items):
    return "\n".join(ICON[l] + t for l, t in items)


def full_report(proxy=PROXY):
    return format_report(analyze(query_all(proxy), local_info(), direct_ip()))
