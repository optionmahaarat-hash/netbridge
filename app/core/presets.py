"""Bypass values that can change WITHOUT a new release.

The filter changes every few weeks and each time only a few numbers move (finalMask lengths/delays, cipherSuites,
fingerprint). Those numbers live in a small JSON file, in layers (later layers win, field by field):

    1. built-in values compiled into the program (app/core/bypass.py)      <- always there, last resort
    2. assets/bypass_presets.json   shipped with the program / the APK
    3. data/bypass_presets.json     the user's file: edited by hand or written by "Update bypass values"

File format:
    {"version": 3, "updated": "2026-10-15",
     "presets": {"pattng": {"label": "...", "fingerprint": "unsafe", "cipherSuites": "A:B",
                            "finalmask": {"tcp": [{"type": "fragment", "settings": {...}}]},
                            "auto": true}}}

A downloaded file is DATA only, but it still ends up inside the Xray config, so it is checked against an allow-list
(known keys, known fingerprints, known mask types, plain scalar settings, size limits). A preset that fails the check is
skipped with a reason; the rest keep working. A broken or missing file never stops the program: the layer below is used.
"""
import copy
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from app.storage.atomic import read_json, write_json_atomic

# Where "Update bypass values" looks. Editing this file in the GitHub repo updates every copy at its next update.
DEFAULT_URL = "https://raw.githubusercontent.com/optionmahaarat-hash/netbridge/main/assets/bypass_presets.json"

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets"
BUNDLED_FILE = ASSETS / "bypass_presets.json"
USER_FILE = Path("data/bypass_presets.json")

RESERVED = {"off", "ech", "custom"}                      # these three have their own logic and cannot be redefined
FINGERPRINTS = {"unsafe", "chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random", "randomized"}
MASK_NETWORKS = {"tcp", "udp"}
MASK_TYPES = {"fragment", "noise"}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
CIPHER_RE = re.compile(r"^[A-Z0-9_]+(?::[A-Z0-9_]+)*$")
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
PRESET_KEYS = {"label", "fingerprint", "cipherSuites", "finalmask", "auto"}
MAX_BYTES = 64 * 1024
MAX_PRESETS = 16
MAX_MASKS = 8


def _scalar(v):
    """Setting values are strings or whole numbers (or short lists of those): never nested objects."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, str)):
        return len(str(v)) <= 64
    return False


def _check_settings(s):
    if not isinstance(s, dict) or len(s) > 12:
        raise ValueError("settings must be a small object")
    for k, v in s.items():
        if not KEY_RE.match(str(k)):
            raise ValueError(f"bad setting name {k!r}")
        if isinstance(v, list):
            if len(v) > 12 or not all(_scalar(x) for x in v):
                raise ValueError(f"setting {k!r} must be a short list of numbers/text")
        elif not _scalar(v):
            raise ValueError(f"setting {k!r} must be a number or text")


def _check_finalmask(fm):
    if not isinstance(fm, dict) or not fm:
        raise ValueError("finalmask must be an object like {\"tcp\": [...]}")
    for net, masks in fm.items():
        if net not in MASK_NETWORKS:
            raise ValueError(f"finalmask network {net!r} is not allowed")
        if not isinstance(masks, list) or not masks or len(masks) > MAX_MASKS:
            raise ValueError(f"finalmask.{net} must be a list of 1-{MAX_MASKS} masks")
        for m in masks:
            if not isinstance(m, dict) or set(m) - {"type", "settings"}:
                raise ValueError("a mask has only 'type' and 'settings'")
            if m.get("type") not in MASK_TYPES:
                raise ValueError(f"mask type {m.get('type')!r} is not allowed")
            _check_settings(m.get("settings", {}))


def check_preset(p):
    """Raises ValueError (with a plain reason) if `p` is not an allowed preset. Returns a cleaned copy."""
    if not isinstance(p, dict):
        raise ValueError("a preset must be an object")
    extra = set(p) - PRESET_KEYS
    if extra:
        raise ValueError("unknown field: " + ", ".join(sorted(map(str, extra))))
    out = {}
    if "label" in p:
        if not isinstance(p["label"], str) or not 0 < len(p["label"]) <= 80:
            raise ValueError("label must be text up to 80 characters")
        out["label"] = p["label"]
    if "fingerprint" in p:
        if p["fingerprint"] not in FINGERPRINTS:
            raise ValueError(f"fingerprint {p['fingerprint']!r} is not allowed")
        out["fingerprint"] = p["fingerprint"]
    if "cipherSuites" in p:
        cs = p["cipherSuites"]
        if not isinstance(cs, str) or len(cs) > 2000 or not CIPHER_RE.match(cs):
            raise ValueError("cipherSuites must be NAMES joined by ':' (capital letters, digits, '_')")
        out["cipherSuites"] = cs
    if "finalmask" in p:
        _check_finalmask(p["finalmask"])
        out["finalmask"] = copy.deepcopy(p["finalmask"])
    if "auto" in p:
        if not isinstance(p["auto"], bool):
            raise ValueError("auto must be true or false")
        out["auto"] = p["auto"]
    return out


def check_doc(doc):
    """-> (clean_doc, errors). clean_doc keeps only the presets that passed; errors are 'name: reason' lines."""
    errors = []
    if not isinstance(doc, dict):
        raise ValueError("the file must contain a JSON object")
    version = doc.get("version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise ValueError("'version' must be a whole number")
    presets = doc.get("presets")
    if not isinstance(presets, dict):
        raise ValueError("'presets' is missing")
    if len(presets) > MAX_PRESETS:
        raise ValueError(f"too many presets (max {MAX_PRESETS})")
    clean = {}
    for name, p in presets.items():
        if name in RESERVED:
            errors.append(f"{name}: this name is reserved"); continue
        if not isinstance(name, str) or not NAME_RE.match(name):
            errors.append(f"{name}: bad name (use a-z, 0-9, _)"); continue
        try:
            clean[name] = check_preset(p)
        except ValueError as e:
            errors.append(f"{name}: {e}")
    out = {"version": version, "presets": clean}
    if isinstance(doc.get("updated"), str):
        out["updated"] = doc["updated"][:32]
    return out, errors


def _load_layer(path, errors):
    """One file -> clean doc or None. Problems are appended to `errors`, never raised."""
    try:
        path = Path(path)
        if not path.exists():
            return None
        raw = read_json(path, None)             # a corrupt file is renamed to .bad and reported as None
        if raw is None:
            errors.append(f"{path.name}: unreadable (kept as .bad)")
            return None
        doc, errs = check_doc(raw)
        errors.extend(f"{path.name} {e}" for e in errs)
        return doc
    except Exception as e:                      # nothing in a data file may stop the program
        errors.append(f"{Path(path).name}: {e}")
        return None


def merge(base, *layers):
    """base = {name: preset}. Each layer is a clean doc. Same name: field by field, the later layer wins."""
    out = {k: copy.deepcopy(v) for k, v in base.items()}
    version = 1
    for doc in layers:
        if not doc:
            continue
        version = max(version, doc.get("version", 0))
        for name, p in doc["presets"].items():
            out[name] = {**out.get(name, {}), **copy.deepcopy(p)}
    return out, version


def load(builtin, bundled=None, user=None):
    """-> {"presets": {...}, "version": int, "errors": [...]}. Paths default to the real files."""
    errors = []
    layers = [_load_layer(bundled or BUNDLED_FILE, errors), _load_layer(user or USER_FILE, errors)]
    presets, version = merge(builtin, *layers)
    return {"presets": presets, "version": version, "errors": errors}


# ---------------------------------------------------------------- updating from the internet
class PresetError(Exception):
    pass


def _opener(proxy):
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    return urllib.request.build_opener(*handlers)


def fetch(url=None, proxy=None, timeout=15):
    """Downloads and checks a presets file. Tries through `proxy` first (when given), then directly.
    Returns (clean_doc, errors). Raises PresetError."""
    url = (url or DEFAULT_URL).strip()
    if not url.lower().startswith("https://"):
        raise PresetError("the update address must start with https://")
    problems = []
    for px in ([proxy, None] if proxy else [None]):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NetBridge"})
            with _opener(px).open(req, timeout=timeout) as r:
                data = r.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise PresetError("the file is too large")
            doc, errs = check_doc(json.loads(data.decode("utf-8")))
            if not doc["presets"]:
                raise PresetError("the file has no usable preset" + (": " + "; ".join(errs[:2]) if errs else ""))
            return doc, errs
        except PresetError:
            raise
        except Exception as e:
            problems.append(f"{type(e).__name__}: {e}")
    raise PresetError("; ".join(problems[:2]) or "download failed")


def install(doc, user_file=None):
    """Writes a CLEAN doc as the user's layer (atomic)."""
    write_json_atomic(user_file or USER_FILE, doc)


def update(current_version, url=None, proxy=None, user_file=None, timeout=15):
    """Download + check + save when the file is newer than `current_version`.
    Returns ("updated" | "current", doc, errors). Raises PresetError."""
    doc, errs = fetch(url, proxy, timeout)
    if doc["version"] <= current_version:
        return "current", doc, errs
    install(doc, user_file)
    return "updated", doc, errs


_LAST = {"t": None}


def auto_update(current_version, proxy=None, every=6 * 3600, timeout=6, now=time.time, **kw):
    """Silent version for AUTO: at most once per `every` seconds per run of the program, short timeout, and every
    failure (offline, blocked, bad file) is swallowed - the values already in use stay. Returns update()'s result or None."""
    if _LAST["t"] is not None and now() - _LAST["t"] < every:
        return None
    _LAST["t"] = now()
    try:
        return update(current_version, proxy=proxy, timeout=timeout, **kw)
    except Exception:
        return None
