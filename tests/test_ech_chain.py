from app.core.config_generator import generate_config, profile_key
from app.core.bypass import ECH_DEFAULT
from app.utils.parser import parse_one

CF = {"name": "cf", "type": "vless", "server": "104.16.1.1", "port": 443,
      "uuid": "123e4567-e89b-12d3-a456-426614174000", "network": "ws", "security": "tls",
      "sni": "a.workers.dev", "host": "a.workers.dev", "path": "/x"}
MAIN = {"name": "main", "type": "vless", "server": "203.0.113.5", "port": 443,
        "uuid": "223e4567-e89b-12d3-a456-426614174000", "network": "tcp", "security": "tls", "sni": "m.example.com"}


def test_ech_mode_sets_config_list_and_chrome():
    p = dict(CF, bypass="ech")
    t = generate_config([p])["outbounds"][0]["streamSettings"]["tlsSettings"]
    assert t["echConfigList"] == ECH_DEFAULT and t["fingerprint"] == "chrome"
    assert "finalmask" not in generate_config([p])["outbounds"][0]["streamSettings"]


def test_ech_custom_value_and_share_link_param():
    p = parse_one("vless://123e4567-e89b-12d3-a456-426614174000@1.1.1.1:443?security=tls&type=ws"
                  "&sni=a.workers.dev&host=a.workers.dev&path=%2Fx&ech=x.com%2Bhttps%3A%2F%2Fdns.google%2Fdns-query#t")
    assert p["ech"] == "x.com+https://dns.google/dns-query"
    t = generate_config([p])["outbounds"][0]["streamSettings"]["tlsSettings"]
    assert t["echConfigList"] == "x.com+https://dns.google/dns-query"


def test_chain_uses_dialer_proxy():
    main = dict(MAIN, chain_key=profile_key(CF))
    cfg = generate_config([main], all_profiles=[CF, main])
    tags = [o["tag"] for o in cfg["outbounds"]]
    assert "hop0" in tags and "p0" in tags
    p0 = next(o for o in cfg["outbounds"] if o["tag"] == "p0")
    assert p0["streamSettings"]["sockopt"]["dialerProxy"] == "hop0"
    # default outbound = first one: it must be the main server, never the hop
    assert cfg["outbounds"][0]["tag"] == "p0"


def test_no_chain_without_profiles():
    main = dict(MAIN, chain_key=profile_key(CF))
    cfg = generate_config([main])
    assert all(o["tag"] != "hop0" for o in cfg["outbounds"])
