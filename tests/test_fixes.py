"""Regression tests for the bugs fixed in the review (see FIXES-fa.md)."""
import base64, json, os, subprocess, sys, types

import pytest

from app.core.config_generator import generate_config
from app.core import routing, system_proxy
from app.lite import engine, updater
from app.protocols.shadowsocks import parse_shadowsocks
from app.protocols.vmess import parse_vmess
from app.storage import atomic, profiles as store_profiles, settings as store_settings
from app.utils.parser import parse_many

UUID = "11111111-1111-1111-1111-111111111111"


def vl(n, **k):
    d = {"name": f"s{n}", "type": "vless", "server": f"h{n}.example.com", "port": 443, "uuid": UUID,
         "network": "tcp", "security": "tls", "sni": f"h{n}.example.com"}
    d.update(k); return d


def test_balancer_does_not_include_pin_exit():
    pin = vl(99)
    cfg = generate_config([vl(i) for i in range(3)], {"routing": {"pin_sites": ["a.com"]}}, mode="auto", pin_profile=pin)
    sel = cfg["routing"]["balancers"][0]["selector"]
    tags = [o["tag"] for o in cfg["outbounds"]]
    assert "pin" in tags
    matched = {t for t in tags if any(t.startswith(s) for s in sel)}
    assert "pin" not in matched and matched == {"p0", "p1", "p2"}
    assert cfg["observatory"]["subjectSelector"] == sel


def test_xhttp_and_httpupgrade_streams():
    c = generate_config([vl(1, network="xhttp", path="/x", host="h.com", xmode="packet-up")])
    ss = c["outbounds"][0]["streamSettings"]
    assert ss["network"] == "xhttp" and ss["xhttpSettings"] == {"path": "/x", "host": "h.com", "mode": "packet-up"}
    c = generate_config([vl(1, network="httpupgrade", path="/u")])
    assert c["outbounds"][0]["streamSettings"]["httpupgradeSettings"] == {"path": "/u"}


def test_parse_many_empty_text_is_not_json():
    assert parse_many("") == ([], [])
    assert parse_many("   \n ") == ([], [])


def test_wrapped_base64_subscription():
    link = f"vless://{UUID}@a.example.com:443?security=tls&type=tcp#a\nvless://{UUID}@b.example.com:443?security=tls&type=tcp#b\n"
    b = base64.b64encode(link.encode()).decode()
    wrapped = "\n".join(b[i:i + 40] for i in range(0, len(b), 40))
    found, errors = parse_many(wrapped)
    assert [p["server"] for p in found] == ["a.example.com", "b.example.com"] and not errors


def test_vmess_grpc_service_name():
    d = {"v": "2", "ps": "g", "add": "x.example.com", "port": "443", "id": UUID, "net": "grpc", "path": "svc", "tls": "tls"}
    p = parse_vmess("vmess://" + base64.b64encode(json.dumps(d).encode()).decode())
    assert p["service_name"] == "svc" and p["port"] == 443
    s = generate_config([p])["outbounds"][0]["streamSettings"]
    assert s["grpcSettings"]["serviceName"] == "svc"


def test_shadowsocks_legacy_link():
    cred = base64.urlsafe_b64encode(b"aes-256-gcm:secret@1.2.3.4:8388").decode().rstrip("=")
    p = parse_shadowsocks(f"ss://{cred}#legacy")
    assert (p["server"], p["port"], p["method"], p["password"], p["name"]) == ("1.2.3.4", 8388, "aes-256-gcm", "secret", "legacy")


def test_routing_host_with_port():
    assert routing.classify("example.com:8443") == ("domain", "domain:example.com")
    assert routing.classify("1.2.3.4") == ("ip", "1.2.3.4")


def test_atomic_write_and_corrupt_file_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(store_profiles, "DATA", tmp_path / "profiles.json")
    store_profiles.save_profiles([{"name": "a"}])
    assert store_profiles.load_profiles() == [{"name": "a"}]
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    (tmp_path / "profiles.json").write_text("{broken", encoding="utf-8")
    assert store_profiles.load_profiles() == []
    assert (tmp_path / "profiles.json.bad").exists()          # kept for recovery, not silently overwritten
    (tmp_path / "profiles.json").write_text('{"not": "a list"}', encoding="utf-8")
    assert store_profiles.load_profiles() == []


def test_settings_wrong_types(tmp_path, monkeypatch):
    monkeypatch.setattr(store_settings, "DATA", tmp_path / "s.json")
    (tmp_path / "s.json").write_text(json.dumps({"mode": "auto", "routing": "oops"}), encoding="utf-8")
    s = store_settings.load_settings()
    assert s["mode"] == "auto" and isinstance(s["routing"], dict)
    monkeypatch.setattr(engine, "SETTINGS", tmp_path / "l.json")
    (tmp_path / "l.json").write_text(json.dumps({"subs": "x"}), encoding="utf-8")
    assert engine.load_settings()["subs"] == []


def test_empty_subscription_does_not_wipe_group(monkeypatch):
    old = vl(1, group="g")
    profiles = [old]
    monkeypatch.setattr(engine, "fetch_subscription", lambda url, proxy=None: ([], []))
    total, failed = engine.refresh_subscriptions(profiles, {"subs": [{"url": "http://x/sub", "group": "g"}]})
    assert profiles == [old] and total == 0 and failed


def test_subscription_refresh_replaces_group(monkeypatch):
    profiles = [vl(1, group="g", delay=50)]
    monkeypatch.setattr(engine, "fetch_subscription", lambda url, proxy=None: ([vl(1), vl(2)], []))
    total, failed = engine.refresh_subscriptions(profiles, {"subs": [{"url": "http://x/sub", "group": "g"}]})
    assert total == 2 and not failed and len(profiles) == 2 and profiles[0].get("delay") == 50


def test_wait_port_gives_up_when_process_died():
    from app.core.delay_all import _wait_port
    dead = types.SimpleNamespace(poll=lambda: 1)
    import time
    t = time.time()
    assert _wait_port(1, timeout=4.0, proc=dead) is False
    assert time.time() - t < 1.0


def test_system_proxy_only_disables_its_own(monkeypatch):
    calls = []
    monkeypatch.setattr(system_proxy, "set_proxy", lambda en, server=None: calls.append(en))
    monkeypatch.setattr(system_proxy, "current", lambda: (True, "10.1.1.1:3128"))       # another app's proxy
    assert system_proxy.disable_if_ours("127.0.0.1:10809") is False and calls == []
    monkeypatch.setattr(system_proxy, "current", lambda: (True, "127.0.0.1:10809"))
    assert system_proxy.disable_if_ours("127.0.0.1:10809") is True and calls == [False]
    monkeypatch.setattr(system_proxy, "current", lambda: (False, ""))
    assert system_proxy.disable_if_ours("127.0.0.1:10809") is False


def test_damaged_manifest_is_update_error():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pub = Ed25519PrivateKey.generate().public_key()
    m = {"app": "NetBridgeLite", "version": "9", "sha256": "0", "size": 1, "url": "u", "signature": "!!!not-base64!!!"}
    with pytest.raises(updater.UpdateError):
        updater.verify_manifest(m, pub)
