"""Import profiles from a sing-box JSON file ({"outbounds": [...]}).
Supports vless (TLS / Reality / ws / grpc), vmess, trojan, shadowsocks, hysteria2."""
import json, re
from app.protocols.shadowsocks import fix_ss

SUPPORTED = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2"}

def parse_singbox(text):
    data = json.loads(text)
    outs = data.get("outbounds") if isinstance(data, dict) else data
    if not isinstance(outs, list):
        raise ValueError("No 'outbounds' list found")
    profiles, errors = [], []
    for o in outs:
        try:
            if not isinstance(o, dict) or o.get("type") not in SUPPORTED:
                continue   # direct / selector / urltest ... are not profiles
            profiles.append(_one(o))
        except Exception as e:
            errors.append((str(o.get("tag", "?"))[:80], str(e)))
    return profiles, errors

def _name(o):
    n = re.sub(r"\s*§\s*\d+\s*$", "", str(o.get("tag") or "")).strip()   # drop the ' § 12' counter
    return n or f"{o.get('server')}:{o.get('server_port')}"

def _one(o):
    t = o["type"]
    server = str(o.get("server") or "").strip()
    if not server or server == "0.0.0.0":
        raise ValueError("empty server")
    p = {"name": _name(o), "type": t, "server": server, "port": int(o["server_port"])}
    tls = o.get("tls") or {}
    if t == "shadowsocks":
        p["method"], p["password"] = fix_ss(o.get("method", ""), o.get("password", ""))
        return p
    if t == "hysteria2":
        p.update(password=str(o.get("password", "")), network="hysteria", security="tls",
                 sni="" if tls.get("disable_sni") else tls.get("server_name", ""))
        if tls.get("insecure"): p["insecure"] = True
        ob = o.get("obfs") or {}
        if ob.get("password"): p["obfs_password"] = ob["password"]
        return p

    tr = o.get("transport") or {}
    net = tr.get("type", "tcp")
    if net not in ("tcp", "ws", "grpc"):
        raise ValueError(f"transport '{net}' not supported")
    p["network"] = net
    if t in ("vless", "vmess"): p["uuid"] = o["uuid"]
    else: p["password"] = o["password"]
    if o.get("flow"): p["flow"] = o["flow"]

    reality = tls.get("reality") or {}
    p["security"] = "reality" if reality.get("enabled") else ("tls" if tls.get("enabled") else "")
    if p["security"]:
        p["sni"] = tls.get("server_name", "")
        p["fp"] = (tls.get("utls") or {}).get("fingerprint", "")
        if tls.get("insecure"): p["insecure"] = True
    if p["security"] == "reality":
        p["pbk"] = reality.get("public_key", "")
        p["sid"] = reality.get("short_id", "")
        if not p["pbk"]: raise ValueError("Reality without public_key")
    elif p["security"] == "tls":
        alpn = tls.get("alpn", "")
        p["alpn"] = ",".join(alpn) if isinstance(alpn, list) else alpn
    if net == "ws":
        p["path"] = tr.get("path", "/")
        p["host"] = (tr.get("headers") or {}).get("Host", "")
        if tr.get("max_early_data"):
            p["early_data"] = int(tr["max_early_data"])
            p["early_data_header"] = tr.get("early_data_header_name", "Sec-WebSocket-Protocol")
    if net == "grpc":
        p["service_name"] = tr.get("service_name", "")
    return p
