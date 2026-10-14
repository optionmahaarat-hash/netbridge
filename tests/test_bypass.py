import json, shutil, subprocess, pathlib, pytest
from app.core.config_generator import generate_xray_config, write_config
from app.core.bypass import CIPHER_SUITES

BASE = {"name": "T", "type": "vless", "server": "1.1.1.1", "port": 443,
        "uuid": "123e4567-e89b-12d3-a456-426614174000", "network": "ws",
        "security": "tls", "sni": "a.workers.dev", "host": "a.workers.dev", "path": "/x"}

def out(**kw):
    return generate_xray_config({**BASE, **kw})["outbounds"][0]["streamSettings"]

def test_off_has_no_bypass():
    s = out()
    assert "finalmask" not in s and "cipherSuites" not in s["tlsSettings"]

def test_standard():
    s = out(bypass="standard")
    assert s["tlsSettings"]["fingerprint"] == "unsafe"
    assert s["tlsSettings"]["cipherSuites"] == CIPHER_SUITES
    assert s["finalmask"]["tcp"][0]["type"] == "fragment"

def test_pattng_exact():
    s = out(bypass="pattng")
    assert s["finalmask"]["tcp"][0]["settings"]["lengths"] == ["0", "104", "1"]
    assert s["finalmask"]["tcp"][1]["settings"]["maxSplit"] == "11"

def test_requires_tls():
    with pytest.raises(ValueError):
        out(bypass="standard", security="")

def test_clean_ip_keeps_sni():
    c = generate_xray_config({**BASE, "address_override": "104.16.1.1", "sni": ""})
    ob = c["outbounds"][0]
    assert ob["settings"]["vnext"][0]["address"] == "104.16.1.1"
    assert ob["streamSettings"]["tlsSettings"]["serverName"] == "1.1.1.1"

XRAY = shutil.which("xray") or "/tmp/xr/xray"
@pytest.mark.skipif(not pathlib.Path(XRAY).exists(), reason="no xray binary")
@pytest.mark.parametrize("mode", ["off", "standard", "custom"])
def test_real_xray_accepts(mode, tmp_path):
    p = tmp_path / "c.json"
    write_config({**BASE, "bypass": mode, "cs": CIPHER_SUITES}, p)
    r = subprocess.run([XRAY, "run", "-test", "-c", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

def test_subscription_base64(monkeypatch):
    import base64, io
    from app.utils import subscription
    link = "vless://123e4567-e89b-12d3-a456-426614174000@1.2.3.4:443?type=ws&security=tls&sni=a.com#A"
    body = base64.b64encode(link.encode())
    class R:
        def read(self, n=-1): return body
    class O:
        def open(self, *a, **k): return R()
    monkeypatch.setattr(subscription.urllib.request, "build_opener", lambda *a: O())
    p, e = subscription.fetch_subscription("https://x/sub")
    assert len(p) == 1 and p[0]["server"] == "1.2.3.4"

def test_inbounds_have_http():
    c = generate_xray_config(BASE)
    assert {i["protocol"] for i in c["inbounds"]} == {"socks", "http"}

def test_singbox_json_import():
    import json
    from app.utils.parser import parse_many
    j = {"outbounds": [
        {"type": "vless", "tag": "a", "server": "x.workers.dev", "server_port": 443,
         "uuid": "123e4567-e89b-12d3-a456-426614174000",
         "tls": {"enabled": True, "server_name": "X.WoRkErS.dev", "alpn": "http/1.1",
                 "utls": {"enabled": True, "fingerprint": "chrome"}},
         "transport": {"type": "ws", "path": "/vl/A", "headers": {"Host": "x.workers.dev"},
                       "max_early_data": 2560}},
        {"type": "trojan", "tag": "b", "server": "1.1.1.1", "server_port": 80, "password": "pw",
         "transport": {"type": "ws", "path": "/tr/B", "headers": {"Host": "x.workers.dev"}}},
        {"type": "direct", "tag": "direct"}]}
    p, e = parse_many(json.dumps(j))
    assert len(p) == 2 and not e
    assert p[0]["security"] == "tls" and p[0]["sni"] == "X.WoRkErS.dev" and p[0]["early_data"] == 2560
    assert p[1]["security"] == ""
    ws = generate_xray_config(p[0])["outbounds"][0]["streamSettings"]["wsSettings"]
    assert ws["maxEarlyData"] == 2560
