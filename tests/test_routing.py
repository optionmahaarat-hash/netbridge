import json, pathlib, shutil, subprocess, pytest
from app.core.routing import classify, build_routing
from app.core.config_generator import generate_config, write_config

VL = {"name": "A", "type": "vless", "server": "1.1.1.1", "port": 443,
      "uuid": "123e4567-e89b-12d3-a456-426614174000", "network": "ws",
      "security": "tls", "sni": "a.workers.dev", "path": "/x"}
VL2 = {**VL, "name": "B", "server": "2.2.2.2"}

def test_classify():
    assert classify("https://www.Digikala.com/cart") == ("domain", "domain:digikala.com")
    assert classify("*.example.ir") == ("domain", "domain:example.ir")
    assert classify("1.2.3.0/24") == ("ip", "1.2.3.0/24")
    assert classify("8.8.8.8") == ("ip", "8.8.8.8")
    assert classify("geosite:category-ir") == ("domain", "geosite:category-ir")
    assert classify("# comment") is None and classify("  ") is None

def test_rules_order_and_asis():
    r = build_routing({"lan": True, "iran": True, "ads": True,
                       "direct": ["bank.com"], "proxy": ["x.ir"]}, {"outboundTag": "p0"})
    assert r["domainStrategy"] == "AsIs"
    tags = [(list(k for k in x if k in ("domain", "ip"))[0], x["outboundTag"]) for x in r["rules"]]
    assert tags[0] == ("domain", "block")                       # ads first
    assert tags[1] == ("domain", "p0")                          # forced proxy beats iran-direct
    direct_domains = [x for x in r["rules"] if x.get("domain") and x["outboundTag"] == "direct"][0]["domain"]
    assert "domain:bank.com" in direct_domains and "geosite:category-ir" in direct_domains
    direct_ips = [x for x in r["rules"] if x.get("ip") and x["outboundTag"] == "direct"][0]["ip"]
    assert "geoip:private" in direct_ips and "geoip:ir" in direct_ips

def test_default_has_only_lan():
    c = generate_config([VL], {"routing": {"lan": True}})
    assert len(c["routing"]["rules"]) == 1 and c["outbounds"][0]["tag"] == "p0"

def test_auto_builds_balancer():
    c = generate_config([VL, VL2], {"routing": {"lan": True}}, mode="auto")
    assert [o["tag"] for o in c["outbounds"][:2]] == ["p0", "p1"]
    assert c["routing"]["balancers"][0]["strategy"]["type"] == "leastPing"
    assert c["routing"]["rules"][-1]["balancerTag"] == "auto" and "observatory" in c

def test_manual_uses_first_only():
    c = generate_config([VL, VL2], {}, mode="manual")
    assert len([o for o in c["outbounds"] if o["tag"].startswith("p")]) == 1

XRAY = shutil.which("xray") or "/tmp/xr/xray"
@pytest.mark.skipif(not pathlib.Path(XRAY).exists(), reason="no xray binary")
@pytest.mark.parametrize("mode", ["manual", "auto"])
def test_real_xray_accepts(mode, tmp_path):
    p = tmp_path / "c.json"
    st = {"routing": {"lan": True, "iran": True, "ads": True,
                      "direct": ["bank.com", "10.0.0.0/8"], "proxy": ["x.ir"]}}
    write_config([VL, VL2, {**VL, "bypass": "pattng", "server": "3.3.3.3"}], p, st, mode=mode)
    r = subprocess.run([XRAY, "run", "-test", "-c", str(p)], capture_output=True, text=True,
                       cwd=str(pathlib.Path(XRAY).parent))
    assert r.returncode == 0, r.stdout + r.stderr

def test_pin_sites_use_dedicated_outbound():
    st = {"routing": {"lan": True, "pin_sites": ["blocks-iran.com"]}}
    c = generate_config([VL], st, pin_profile=VL2)
    tags = [o["tag"] for o in c["outbounds"]]
    assert "pin" in tags and c["outbounds"][0]["tag"] == "p0"
    first = c["routing"]["rules"][0]
    assert first["outboundTag"] == "pin" and first["domain"] == ["domain:blocks-iran.com"]
    assert "pin" not in [o["tag"] for o in generate_config([VL], st)["outbounds"]]   # no profile -> no rule

@pytest.mark.skipif(not pathlib.Path(XRAY).exists(), reason="no xray binary")
def test_real_xray_accepts_pin(tmp_path):
    p = tmp_path / "c.json"
    write_config([VL, VL2], p, {"routing": {"iran": True, "pin_sites": ["a.com"]}}, mode="auto", pin_profile=VL2)
    r = subprocess.run([XRAY, "run", "-test", "-c", str(p)], capture_output=True, text=True, cwd=str(pathlib.Path(XRAY).parent))
    assert r.returncode == 0, r.stdout + r.stderr
