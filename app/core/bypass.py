"""Bypass presets: Fragment (finalmask) + fingerprint 'unsafe' + cipherSuites.

Based on the PattNG method: only works for TLS configs, because it changes the
first TLS message (ClientHello) that a filter can read.
"""
import copy
import json

from app.core import presets as _presets

CIPHER_SUITES = (
    "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256:"
    "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384:"
    "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256:TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256:"
    "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256:TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256:"
    "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA:TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA:"
    "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256:TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256"
)

# EXACT values from the video/guide. Uses "lengths"/"delays" arrays with 0 entries.
# Verified: accepted by official Xray 26.7.28, rejected by older 26.3.27
# ("LengthMin can't be 0"). So it needs a recent official Xray-core (>= 26.7).
FM_PATTNG = {"tcp": [
    {"type": "fragment", "settings": {"packets": "tlshello", "lengths": ["0", "104", "1"],
                                       "delays": ["0"], "maxSplit": "0"}},
    {"type": "fragment", "settings": {"packets": "1-1", "lengths": ["114", "1"],
                                       "delays": ["1"], "maxSplit": "11"}},
]}

# Works on older Xray-core too (verified with `xray run -test`). These numbers are
# a generic starting point, NOT from the guide; tune them if it does not connect.
FM_STANDARD = {"tcp": [
    {"type": "fragment", "settings": {"packets": "tlshello", "length": "10-30",
                                       "delay": "10-20", "maxSplit": "0"}},
]}

# ECH (video method 1): the real site name is encrypted inside the ClientHello, the filter only sees
# the public name. Xray fetches the ECH keys itself: "<public name>+<DoH url>". The DoH address must be
# reachable from YOUR network (1.1.1.1 is often blocked; try https://dns.google/dns-query, a local
# resolver, or an IP that works for you).
ECH_DEFAULT = "cloudflare-ech.com+https://1.1.1.1/dns-query"

def ech_value(v):
    """'1'/'true'/'auto' -> default query string; anything else is used as given."""
    if v is True or str(v).strip().lower() in ("1", "true", "yes", "on", "auto"):
        return ECH_DEFAULT
    return str(v).strip()

# ---- values that can be updated without a release (see app/core/presets.py) ------------------------------------
# The built-in values below are the last resort; assets/bypass_presets.json and data/bypass_presets.json win over them.
BUILTIN = {
    "standard": {"label": "Fragment + unsafe (works on older Xray too)", "fingerprint": "unsafe",
                 "cipherSuites": CIPHER_SUITES, "finalmask": FM_STANDARD, "auto": True},
    "pattng": {"label": "Video/PattNG exact (needs Xray 26.7 or newer)", "fingerprint": "unsafe",
               "cipherSuites": CIPHER_SUITES, "finalmask": FM_PATTNG, "auto": True},
}
_FIXED_LABELS = {
    "off": "Off",
    "ech": "ECH (video method 1: encrypted SNI, fingerprint chrome)",
    "custom": "Custom (use finalMask / cipherSuites fields)",
}

# PRESETS (code -> label) is filled by reload(); it is updated IN PLACE so `from app.core.bypass import PRESETS` stays valid.
PRESETS = {}
_PRESETS = {}            # code -> preset dict (fingerprint / cipherSuites / finalmask / auto)
STATE = {"version": 1, "errors": []}


def reload(bundled=None, user=None):
    """(Re)reads the preset files. Never raises: on any problem the built-in values stay in force."""
    try:
        res = _presets.load(BUILTIN, bundled, user)
    except Exception as e:
        res = {"presets": BUILTIN, "version": 1, "errors": [f"presets: {e}"]}
    _PRESETS.clear(); _PRESETS.update(res["presets"])
    PRESETS.clear()
    PRESETS["off"] = _FIXED_LABELS["off"]
    PRESETS["ech"] = _FIXED_LABELS["ech"]
    for name, p in _PRESETS.items():
        PRESETS[name] = p.get("label") or name
    PRESETS["custom"] = _FIXED_LABELS["custom"]
    STATE["version"], STATE["errors"] = res["version"], res["errors"]
    return STATE


def get_preset(name):
    """The preset dict for a method code ('pattng', 'standard', or one added by a file), else None."""
    p = _PRESETS.get(name)
    return copy.deepcopy(p) if p else None


def auto_names():
    """Method codes AUTO should try (after 'off'), in a stable order: pattng, standard, then the extras."""
    first = [n for n in ("pattng", "standard") if _PRESETS.get(n, {}).get("auto", True)]
    rest = [n for n, p in _PRESETS.items() if n not in ("pattng", "standard") and p.get("auto", False)]
    return first + rest


def apply_bypass(profile, stream):
    """Mutates the xray streamSettings dict according to profile['bypass']."""
    mode = profile.get("bypass") or "off"
    tls = stream.get("tlsSettings")
    if mode == "off":
        # Still honour values that came from a share link (fm / cs / fp).
        if profile.get("fm"):
            stream["finalmask"] = _load(profile["fm"], "finalMask")
        if tls is not None and profile.get("cs"):
            tls["cipherSuites"] = profile["cs"]
        if tls is not None and profile.get("ech"):
            tls["echConfigList"] = ech_value(profile["ech"])
        return stream
    if stream.get("security") != "tls" or tls is None:
        raise ValueError("Bypass needs a TLS config (security=tls).")
    tls["fingerprint"] = (profile.get("fp") or "unsafe") if mode == "custom" else "unsafe"
    if mode == "ech":
        # ECH is its own method: no fragment, no cipher tricks, normal browser fingerprint.
        tls["fingerprint"] = profile.get("fp") or "chrome"
        tls["echConfigList"] = ech_value(profile.get("ech") or True)
        return stream
    if mode == "custom":
        if profile.get("cs"):
            tls["cipherSuites"] = profile["cs"].strip().replace("\n", "").replace(" ", "")
        if profile.get("fm"):
            stream["finalmask"] = _load(profile["fm"], "finalMask")
    else:
        preset = get_preset(mode)
        if preset is None:
            raise ValueError(f"Unknown bypass mode: {mode}")
        tls["fingerprint"] = preset.get("fingerprint", "unsafe")
        if preset.get("cipherSuites"):
            tls["cipherSuites"] = preset["cipherSuites"]
        if preset.get("finalmask"):
            stream["finalmask"] = preset["finalmask"]
    if profile.get("ech"):
        tls["echConfigList"] = ech_value(profile["ech"])
    return stream

def _load(text, what):
    if isinstance(text, dict):
        return text
    try:
        return json.loads(text)
    except Exception as e:
        raise ValueError(f"{what} is not valid JSON: {e}")


reload()
