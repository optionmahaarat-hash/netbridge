import json
from pathlib import Path

from app.storage.atomic import read_json, write_json_atomic

DATA = Path("data/settings.json")

DEFAULTS = {
    "free_auto": False,        # refresh the public config list once a day when the app starts
    "free_last": 0,            # unix time of the last successful refresh
    "mode": "manual",          # manual | best | auto
    "group": "",               # selected group filter ("" = all)
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
        s["free_auto"] = bool(data.get("free_auto", s["free_auto"]))
        s["free_last"] = data["free_last"] if isinstance(data.get("free_last"), (int, float)) else 0
        if isinstance(data.get("routing"), dict):
            s["routing"].update(data["routing"])
    return s

def save_settings(s):
    write_json_atomic(DATA, s)
