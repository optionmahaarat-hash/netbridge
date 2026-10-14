"""Routing rules: which sites skip the tunnel (direct) and which are forced through it.

Why some sites 'do not accept the location': they see a foreign / datacenter IP.
The fix is per-site split tunneling - those sites are sent out with your real IP.

domainStrategy is deliberately 'AsIs': we never resolve domains with the local DNS
for matching. (Local DNS in some networks answers blocked domains with fake private
IPs like 10.10.34.x; resolving them would wrongly match the 'private -> direct' rule.)
So domain rules match domain names, IP rules match only when the target is an IP.
"""
import ipaddress
import re
from urllib.parse import urlparse

DOMAIN_PREFIXES = ("domain:", "full:", "regexp:", "keyword:", "geosite:", "ext:")
IP_PREFIXES = ("geoip:", "ext-ip:")

IRAN_DOMAINS = ["geosite:category-ir", r"regexp:\.ir$"]
IRAN_IPS = ["geoip:ir"]
ADS_DOMAINS = ["geosite:category-ads-all"]
LAN_IPS = ["geoip:private"]


# Ready-made site lists for "Sites that reject Iranian IPs" (a name also covers its subdomains).
SERVICE_PRESETS = {
    "OpenAI / ChatGPT": ["openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com", "sora.com"],
    "Anthropic / Claude": ["claude.ai", "claude.com", "anthropic.com"],
    "Google AI (Gemini, AI Studio)": ["gemini.google.com", "aistudio.google.com", "ai.google.dev",
                                      "generativelanguage.googleapis.com", "notebooklm.google.com"],
    "Spotify": ["spotify.com", "scdn.co", "spotifycdn.com"],
    "Netflix": ["netflix.com", "nflxvideo.net", "nflximg.net", "nflxext.com", "nflxso.net"],
}

# Smart DNS ("sanction-breaking DNS"): resolves some blocked sites to a foreign proxy IP.
SDNS_PRESETS = {"Shecan": "178.22.122.100", "Shecan (2)": "185.51.200.2"}


def parse_dns_server(text):
    """'1.2.3.4' or '1.2.3.4:5353' -> (ip, port). Raises ValueError if it is not an IP address."""
    t = (text or "").strip()
    port = 53
    if t.count(":") == 1:
        t, p = t.split(":")
        port = int(p)
        if not 0 < port < 65536:
            raise ValueError("bad DNS port")
    ipaddress.ip_address(t)
    return t, port


def sdns_active(r):
    """(ip, port, [domain rules]) when Smart DNS is configured, else None."""
    if not r or not (r.get("sdns_server") or "").strip():
        return None
    ip, port = parse_dns_server(r["sdns_server"])
    domains, _ = split_entries(r.get("sdns_sites"))
    return (ip, port, domains) if domains else None


def build_dns(r):
    """Xray 'dns' section: only the chosen sites are resolved by the Smart DNS server."""
    a = sdns_active(r)
    if not a:
        return None
    ip, port, domains = a
    return {"servers": [{"address": ip, "port": port, "domains": domains, "skipFallback": True}, "localhost"],
            "queryStrategy": "UseIPv4"}


def classify(entry):
    """'example.com' -> ('domain', 'domain:example.com'); '1.2.3.0/24' -> ('ip', ...)."""
    e = entry.strip()
    if not e or e.startswith("#"):
        return None
    low = e.lower()
    if low.startswith(DOMAIN_PREFIXES):
        return "domain", e
    if low.startswith(IP_PREFIXES):
        return "ip", e
    if "://" in e:                                  # pasted a full URL
        e = urlparse(e).hostname or ""
    e = e.split("/")[0] if not re.fullmatch(r"[0-9a-fA-F:.]+/\d+", e) else e
    e = e.strip().lstrip("*.").rstrip(".")
    if e.count(":") == 1 and e.rsplit(":", 1)[1].isdigit():        # host:port -> host (rules match names, not ports)
        e = e.rsplit(":", 1)[0]
    if not e:
        return None
    try:
        ipaddress.ip_network(e, strict=False)
        return "ip", e
    except ValueError:
        pass
    if e.lower().startswith("www."):
        e = e[4:]
    return "domain", "domain:" + e.lower()


def split_entries(lines):
    domains, ips = [], []
    for line in lines or []:
        c = classify(line)
        if not c: continue
        (domains if c[0] == "domain" else ips).append(c[1])
    return domains, ips


def build_routing(r, target, pin=False):
    """r = settings['routing']. target = {'outboundTag': 'p0'} or {'balancerTag': 'auto'}.
    Returns (routing dict, balancer-needed bool). First matching rule wins."""
    rules = []

    def add(kind, values, **dest):
        if values:
            rules.append({"type": "field", kind: values, **dest})

    if r.get("ads"):
        add("domain", ADS_DOMAINS, outboundTag="block")
    if pin:                                         # sites that reject Iranian IPs -> chosen exit server
        sd, si = split_entries(r.get("pin_sites"))
        add("domain", sd, outboundTag="pin")
        add("ip", si, outboundTag="pin")
    sd_active = sdns_active(r)
    if sd_active:                                   # Smart DNS: DNS server itself and its sites leave directly
        add("ip", [sd_active[0]], outboundTag="direct")
        add("domain", sd_active[2], outboundTag="sdns")
    pd, pi = split_entries(r.get("proxy"))          # forced through the tunnel
    add("domain", pd, **target)
    add("ip", pi, **target)
    dd, di = split_entries(r.get("direct"))         # skip the tunnel
    if r.get("lan", True):
        di = LAN_IPS + di
    if r.get("iran"):
        dd = dd + IRAN_DOMAINS
        di = di + IRAN_IPS
    add("domain", dd, outboundTag="direct")
    add("ip", di, outboundTag="direct")
    return {"domainStrategy": "AsIs", "rules": rules}
