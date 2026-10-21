import json
from app.storage.atomic import write_text_atomic
from app.core import worker_exit
from app.core.bypass import apply_bypass
from app.core.routing import build_routing, build_dns

def profile_key(p):
    return "|".join(str(p.get(k, "")) for k in ("type", "server", "port", "uuid", "password"))

def _chain_hop(p, all_profiles):
    """Profile that must carry the traffic to p's server (video method 3: Cloudflare config -> main config)."""
    key = p.get("chain_key")
    if not key or not all_profiles:
        return None
    for q in all_profiles:
        if profile_key(q) == key and profile_key(q) != profile_key(p):
            return q
    return None

def _addr(p):
    # Clean-IP trick: connect to another IP, SNI/Host stay the same.
    return (p.get("address_override") or "").strip() or p["server"]

def _stream(p):
    network = p.get("network") or "tcp"
    security = p.get("security") or ""
    path = worker_exit.apply(p.get("path") or "/", p.get("worker_exit"))
    s = {"network": network}
    if security:
        s["security"] = security
    if network == "ws":
        s["wsSettings"] = {"path": path}
        if p.get("host"):
            s["wsSettings"]["headers"] = {"Host": p["host"]}
        if p.get("early_data"):
            s["wsSettings"]["maxEarlyData"] = int(p["early_data"])
            s["wsSettings"]["earlyDataHeaderName"] = p.get("early_data_header") or "Sec-WebSocket-Protocol"
    if security == "tls":
        t = {}
        sni = p.get("sni") or (p["server"] if p.get("address_override") else "")
        if sni: t["serverName"] = sni
        if p.get("fp"): t["fingerprint"] = p["fp"]
        if p.get("alpn"):
            t["alpn"] = [x.strip() for x in p["alpn"].split(",") if x.strip()]
        _cert_policy(t, p)
        s["tlsSettings"] = t
    elif security == "reality":
        r = {"serverName": p.get("sni", ""), "fingerprint": p.get("fp") or "chrome",
             "publicKey": p.get("pbk", ""), "shortId": p.get("sid", "")}
        if p.get("spx"): r["spiderX"] = p["spx"]
        s["realitySettings"] = r
    if network == "grpc":
        s["grpcSettings"] = {"serviceName": p.get("service_name", "")}
    elif network == "httpupgrade":
        s["httpupgradeSettings"] = {"path": path}
        if p.get("host"):
            s["httpupgradeSettings"]["host"] = p["host"]
    elif network in ("xhttp", "splithttp"):
        s["network"] = "xhttp"
        x = {"path": path}
        if p.get("host"):
            x["host"] = p["host"]
        if p.get("xmode"):
            x["mode"] = p["xmode"]
        s["xhttpSettings"] = x
    return apply_bypass(p, s)

def _cert_policy(t, p):
    """Xray >= 26.7 removed allowInsecure. A self-signed server needs its certificate hash pinned."""
    if p.get("pcs"):
        t["pinnedPeerCertSha256"] = str(p["pcs"]).replace(":", "").strip().lower()
    elif p.get("insecure"):
        raise ValueError("Self-signed certificate: not pinned yet. Use the 'Pin certs' button "
                         "(Xray 26.7+ removed allowInsecure).")

def build_outbound(p):
    typ = p["type"]
    if typ in ("shadowsocks", "hysteria2") and (p.get("bypass") or "off") != "off":
        raise ValueError("Bypass (fragment) is only for TLS over TCP profiles.")
    if typ == "vless":
        user = {"id": p["uuid"], "encryption": "none"}
        if p.get("flow"): user["flow"] = p["flow"]
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{
                "address": _addr(p), "port": int(p["port"]), "users": [user]
            }]},
            "streamSettings": _stream(p)
        }
    elif typ == "vmess":
        outbound = {
            "protocol": "vmess",
            "settings": {"vnext": [{
                "address": _addr(p), "port": int(p["port"]),
                "users": [{"id": p["uuid"], "alterId": 0, "security": "auto"}]
            }]},
            "streamSettings": _stream(p)
        }
    elif typ == "trojan":
        outbound = {
            "protocol": "trojan",
            "settings": {"servers": [{
                "address": _addr(p), "port": int(p["port"]),
                "password": p["password"]
            }]},
            "streamSettings": _stream(p)
        }
    elif typ == "shadowsocks":
        outbound = {
            "protocol": "shadowsocks",
            "settings": {"servers": [{
                "address": _addr(p), "port": int(p["port"]),
                "method": p["method"], "password": p["password"]
            }]}
        }
    elif typ == "socks":                      # a local SOCKS5 program, e.g. the Aether core (WARP)
        outbound = {"protocol": "socks",
                    "settings": {"servers": [{"address": p.get("server") or "127.0.0.1", "port": int(p["port"])}]}}
    elif typ == "hysteria2":
        tls = {"alpn": ["h3"]}
        if p.get("sni"): tls["serverName"] = p["sni"]
        _cert_policy(tls, p)
        s = {"network": "hysteria", "security": "tls", "tlsSettings": tls,
             "hysteriaSettings": {"version": 2, "auth": p["password"]}}
        if p.get("obfs_password"):
            s["finalmask"] = {"udp": [{"type": "salamander", "settings": {"password": p["obfs_password"]}}]}
        outbound = {"protocol": "hysteria",
                    "settings": {"version": 2, "address": _addr(p), "port": int(p["port"])},
                    "streamSettings": s}
    else:
        raise ValueError("Unsupported protocol")

    return outbound

def generate_config(profiles, settings=None, mode="manual",
                    socks_port=10808, http_port=10809, loglevel="warning", pin_profile=None,
                    all_profiles=None):
    """profiles: list of profile dicts. mode 'manual' uses profiles[0];
    mode 'auto' builds an Xray balancer (leastPing) over all of them, like Hiddify 'Auto'."""
    if not profiles:
        raise ValueError("No profiles")
    if mode != "auto":
        profiles = profiles[:1]
    outs, hops = [], []
    for i, p in enumerate(profiles):
        o = build_outbound(p)
        o["tag"] = f"p{i}"
        hop = _chain_hop(p, all_profiles)
        if hop is not None:
            # Xray dials p's server THROUGH the hop outbound: you -> hop (Cloudflare Worker) -> p's server.
            h = build_outbound(hop)
            h["tag"] = f"hop{i}"
            ss = o.setdefault("streamSettings", {"network": "tcp"})
            ss.setdefault("sockopt", {})["dialerProxy"] = h["tag"]
            hops.append(h)          # after the p* outbounds: with no routing rule Xray uses the FIRST outbound
        outs.append(o)
    outs += hops
    if pin_profile:                      # dedicated exit for sites that reject Iranian IPs
        o = build_outbound(pin_profile)
        o["tag"] = "pin"
        outs.append(o)
    r = (settings or {}).get("routing", {})
    dns = build_dns(r)
    if dns:                              # direct exit that resolves names with the Smart DNS server
        outs.append({"protocol": "freedom", "tag": "sdns", "settings": {"domainStrategy": "UseIPv4"}})
    outs += [{"protocol": "freedom", "tag": "direct"},
             {"protocol": "blackhole", "tag": "block"}]

    auto = mode == "auto" and len(profiles) > 1
    target = {"balancerTag": "auto"} if auto else {"outboundTag": "p0"}
    routing = build_routing((settings or {}).get("routing", {}), target, pin=bool(pin_profile))
    cfg = {"log": {"loglevel": loglevel}}
    if dns:
        cfg["dns"] = dns
    if auto:
        # Explicit tags: the old prefix "p" also matched the "pin" exit and put it into the balancer.
        sel = [f"p{i}" for i in range(len(profiles))]
        routing["balancers"] = [{"tag": "auto", "selector": sel,
                                 "strategy": {"type": "leastPing"}, "fallbackTag": "p0"}]
        routing["rules"].append({"type": "field", "network": "tcp,udp", "balancerTag": "auto"})
        cfg["observatory"] = {"subjectSelector": sel, "probeInterval": "30s",
                              "probeUrl": "https://www.gstatic.com/generate_204"}
    cfg["routing"] = routing
    sniff = {"enabled": True, "destOverride": ["http", "tls"], "routeOnly": True}
    inbounds = []
    if socks_port:
        inbounds.append({"listen": "127.0.0.1", "port": socks_port, "protocol": "socks",
                         "settings": {"udp": True}, "sniffing": sniff})
    if http_port:
        inbounds.append({"listen": "127.0.0.1", "port": http_port, "protocol": "http",
                         "settings": {}, "sniffing": sniff})
    cfg["inbounds"] = inbounds
    cfg["outbounds"] = outs
    return cfg

def generate_xray_config(p, settings=None):
    """Single profile (kept for backward compatibility)."""
    return generate_config([p], settings)

def write_config(p, path, settings=None, **kw):
    """p: one profile dict, or a list of profiles (use mode='auto')."""
    path.parent.mkdir(parents=True, exist_ok=True)
    profiles = p if isinstance(p, list) else [p]
    data = generate_config(profiles, settings, **kw)
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))   # xray never reads a half-written file
    return data
