import base64
from app.protocols.vless import parse_vless
from app.protocols.vmess import parse_vmess
from app.protocols.trojan import parse_trojan
from app.protocols.shadowsocks import parse_shadowsocks
from app.protocols.hysteria2 import parse_hysteria2

PARSERS = {
    "vless://": parse_vless,
    "vmess://": parse_vmess,
    "trojan://": parse_trojan,
    "ss://": parse_shadowsocks,
    "hysteria2://": parse_hysteria2,
    "hy2://": parse_hysteria2,
}

def parse_one(text):
    text = text.strip()
    for prefix, fn in PARSERS.items():
        if text.lower().startswith(prefix):
            return fn(text)
    raise ValueError("Unsupported config URI")

def parse_many(text):
    if text.lstrip()[:1] and text.lstrip()[:1] in "{[":
        from app.utils.singbox_import import parse_singbox
        try:
            return parse_singbox(text)
        except Exception as e:
            return [], [("json", str(e))]
    text = text.replace("\r", "")
    lines = [x.strip() for x in text.split("\n") if x.strip() and not x.strip().startswith("#")]
    # Support base64 subscription payloads (also when the provider wraps the base64 over several lines).
    if lines and not any("://" in x for x in lines):
        raw = "".join(lines)
        try:
            raw += "=" * (-len(raw) % 4)
            decoded = base64.b64decode(raw.replace("-", "+").replace("_", "/")).decode("utf-8")
            if "://" in decoded:
                lines = [x.strip() for x in decoded.splitlines() if x.strip() and not x.strip().startswith("#")]
        except Exception:
            pass
    result = []
    errors = []
    for line in lines:
        try:
            result.append(parse_one(line))
        except Exception as e:
            errors.append((line[:80], str(e)))
    return result, errors
