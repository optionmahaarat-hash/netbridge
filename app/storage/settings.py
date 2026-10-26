import json
from pathlib import Path

from app.storage.atomic import read_json, write_json_atomic

DATA = Path("data/settings.json")

DEFAULTS = {
    "free_auto": False,        # refresh the public config list once a day when the app starts
    "free_last": 0,            # unix time of the last successful refresh
    "mode": "manual",          # manual | best | auto
    "use_ech": True,           # False: AUTO skips every ECH method (Cloudflare ECH is blocked on many networks)
    "firewall": "auto",        # auto | mci | irancell: which operator firewall AUTO should try first
    "group": "",               # selected group filter ("" = all)
    "doh_extra": [],           # DoH URLs found by the resolver scan; AUTO tries them first for the ECH key lookup
    "routing": {
        "lan": True,           # local network goes direct
        "iran": False,         # Iranian sites go direct (they reject foreign IPs)
        "ads": False,          # block ads
        "direct": [],          # extra sites/IPs that skip the tunnel
        "proxy": [],           # sites that must always use the tunnel
        "pin_sites": [],       # sites that reject Iranian IPs -> go out via pin_profile
        "pin_profile": "",     # key of the profile used as their exit server
    },
}

def load_settings():
    s = json.loads(json.dumps(DEFAULTS))
    data = read_json(DATA, {})
    if isinstance(data, dict):
        s["mode"] = data.get("mode", s["mode"])
        s["group"] = data.get("group", s["group"])
        s["firewall"] = data.get("firewall") if data.get("firewall") in ("auto", "mci", "irancell") else s["firewall"]
        s["use_ech"] = bool(data.get("use_ech", s["use_ech"]))
        d = data.get("doh_extra")
        s["doh_extra"] = [u for u in d if isinstance(u, str) and u.startswith("https://")][:6] if isinstance(d, list) else []
        s["free_auto"] = bool(data.get("free_auto", s["free_auto"]))
        s["free_last"] = data["free_last"] if isinstance(data.get("free_last"), (int, float)) else 0
        if isinstance(data.get("routing"), dict):
            s["routing"].update(data["routing"])
    return s

def save_settings(s):
    write_json_atomic(DATA, s)
