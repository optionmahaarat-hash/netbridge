"""Bypass presets: Fragment (finalmask) + fingerprint 'unsafe' + cipherSuites.

Based on the PattNG method: only works for TLS configs, because it changes the
first TLS message (ClientHello) that a filter can read.
"""
import json

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

PRESETS = {
    "off": "Off",
    "ech": "ECH (video method 1: encrypted SNI, fingerprint chrome)",
    "standard": "Fragment + unsafe (works on older Xray too)",
    "pattng": "Video/PattNG exact (needs Xray 26.7 or newer)",
    "custom": "Custom (use finalMask / cipherSuites fields)",
}

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
    if mode == "standard":
        tls["cipherSuites"] = CIPHER_SUITES
        stream["finalmask"] = json.loads(json.dumps(FM_STANDARD))
    elif mode == "pattng":
        tls["cipherSuites"] = CIPHER_SUITES
        stream["finalmask"] = json.loads(json.dumps(FM_PATTNG))
    elif mode == "custom":
        if profile.get("cs"):
            tls["cipherSuites"] = profile["cs"].strip().replace("\n", "").replace(" ", "")
        if profile.get("fm"):
            stream["finalmask"] = _load(profile["fm"], "finalMask")
    else:
        raise ValueError(f"Unknown bypass mode: {mode}")
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
