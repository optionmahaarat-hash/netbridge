"""Entries copied in shape from a real sing-box export (Reality, gRPC, vmess, SS incl. broken ones, Hysteria2)."""
import json, pathlib, shutil, subprocess, pytest
from app.utils.parser import parse_many
from app.utils.validator import validate_profile
from app.core.config_generator import generate_config, write_config

UUID = "d65cc14c-f53f-4fe2-b262-97856601319c"
OUTS = [
 {"type": "vless", "tag": "Reality § 4", "server": "169.40.42.35", "server_port": 443, "uuid": UUID,
  "flow": "xtls-rprx-vision", "tls": {"enabled": True, "server_name": "yahoo.com",
  "utls": {"enabled": True, "fingerprint": "ios"},
  "reality": {"enabled": True, "public_key": "e2RLf57Li_-MDZGE9ss1BWPgP54mqRb5PfXhW2jcVVg", "short_id": "c39cc7310a"}}},
 {"type": "vless", "tag": "grpc plain", "server": "66.90.104.43", "server_port": 2083, "uuid": UUID,
  "transport": {"type": "grpc", "service_name": "vless"}},
 {"type": "vless", "tag": "reality+grpc", "server": "md5.example.com", "server_port": 443, "uuid": UUID,
  "tls": {"enabled": True, "server_name": "md5.example.com", "alpn": "h2", "utls": {"enabled": True, "fingerprint": "firefox"},
  "reality": {"enabled": True, "public_key": "99MRki6b93wC-hhDHe9yq3IXE3KtPGw4RkFAnpI-8gg", "short_id": "aa9884f2982b7d3c"}},
  "transport": {"type": "grpc", "service_name": "app.v1.PushService"}},
 {"type": "vmess", "tag": "vm", "server": "216.106.187.60", "server_port": 22324, "uuid": "04621bae-ab36-11ec-b909-0242ac120002", "security": "auto"},
 {"type": "shadowsocks", "tag": "ss ok", "server": "5.78.51.123", "server_port": 1080, "method": "chacha20-ietf-poly1305", "password": "8tmnvX5zYuWGVIDP2jglZw"},
 {"type": "shadowsocks", "tag": "ss hidden 2022", "server": "85.133.250.3", "server_port": 8443, "method": "none",
  "password": "MjAyMi1ibGFrZTMtYWVzLTEyOC1nY206RGlnOXQ0RThyZHlkVjEzNzRiM0V1dz09OjQyeUhaYkdKTzg3dkpveWlRdnpEcHc9PQ"},
 {"type": "shadowsocks", "tag": "ss hidden chacha", "server": "3.112.130.53", "server_port": 8316, "method": "none",
  "password": "Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpsanFkYWx1MTMuLg"},
 {"type": "shadowsocks", "tag": "ss cfb (unsupported)", "server": "18.189.171.163", "server_port": 443, "method": "aes-256-cfb", "password": "x"},
 {"type": "shadowsocks", "tag": "fake", "server": "0.0.0.0", "server_port": 1, "method": "aes-256-gcm", "password": "123456"},
 {"type": "shadowsocks", "tag": "empty", "server": "", "server_port": 443, "method": "none", "password": "x"},
 {"type": "hysteria2", "tag": "hy2 obfs § 38", "server": "31.76.80.69", "server_port": 443,
  "obfs": {"type": "salamander", "password": "uw9b2qq5rx"}, "password": "6aab8efdf13945829ae3699c342be406",
  "tls": {"enabled": True, "server_name": "fiproxy1.lockdwn.com"}},
 {"type": "hysteria2", "tag": "hy2 no sni", "server": "179.61.132.96", "server_port": 8443,
  "obfs": {"type": "salamander", "password": "KevinZakarian"}, "password": "KevinZakarian",
  "tls": {"enabled": True, "disable_sni": True, "server_name": "179.61.132.96", "insecure": True}},
 {"type": "direct", "tag": "direct"},
]

def loaded():
    return parse_many(json.dumps({"outbounds": OUTS}))

def test_import_all_types():
    p, e = loaded()
    by = {x["name"]: x for x in p}
    assert by["Reality"]["security"] == "reality" and by["Reality"]["pbk"] and by["Reality"]["flow"] == "xtls-rprx-vision"
    assert by["grpc plain"]["network"] == "grpc" and by["grpc plain"]["service_name"] == "vless"
    assert by["reality+grpc"]["security"] == "reality" and by["reality+grpc"]["network"] == "grpc"
    assert by["vm"]["type"] == "vmess"
    assert by["hy2 obfs"]["type"] == "hysteria2" and by["hy2 obfs"]["obfs_password"] == "uw9b2qq5rx"   # ' § 38' stripped
    assert by["hy2 no sni"]["sni"] == "" and by["hy2 no sni"]["insecure"]

def test_hidden_ss_credentials_recovered():
    by = {x["name"]: x for x in loaded()[0]}
    assert by["ss hidden 2022"]["method"] == "2022-blake3-aes-128-gcm" and ":" in by["ss hidden 2022"]["password"]
    assert by["ss hidden chacha"]["method"] == "chacha20-ietf-poly1305"

def test_bad_entries_rejected():
    p, e = loaded()
    ok = [x["name"] for x in p if not validate_profile(x)]
    bad = [x["name"] for x in p if validate_profile(x)]
    assert "ss cfb (unsupported)" in bad                 # method Xray cannot do
    assert {x[0] for x in e} == {"fake", "empty"}        # fake/empty server rejected by the importer
    assert "Reality" in ok and "hy2 obfs" in ok and "ss hidden 2022" in ok

def test_bypass_refused_for_udp_and_ss():
    p = {x["name"]: x for x in loaded()[0]}
    for n in ("hy2 obfs", "ss hidden chacha"):
        with pytest.raises(ValueError):
            generate_config([{**p[n], "bypass": "standard"}])

def test_hy2_uri_roundtrip():
    from app.ui.main_window import MainWindow
    p = {x["name"]: x for x in loaded()[0]}["hy2 obfs"]
    p2, _ = parse_many(MainWindow.to_uri(None, p))
    assert p2[0]["password"] == p["password"] and p2[0]["obfs_password"] == p["obfs_password"] and p2[0]["sni"] == p["sni"]

def test_ss_vmess_uri_roundtrip():
    from app.ui.main_window import MainWindow
    for n in ("ss ok", "vm"):
        p = {x["name"]: x for x in loaded()[0]}[n]
        p2, e = parse_many(MainWindow.to_uri(None, p))
        assert p2 and p2[0]["server"] == p["server"] and p2[0]["port"] == p["port"] and p2[0]["type"] == p["type"]

XRAY = shutil.which("xray") or "/tmp/xr/xray"
@pytest.mark.skipif(not pathlib.Path(XRAY).exists(), reason="no xray binary")
def test_every_valid_profile_accepted_by_real_xray(tmp_path):
    good = [x for x in loaded()[0] if not validate_profile(x) and (not x.get("insecure") or x.get("pcs"))]
    assert len(good) >= 8
    for i, x in enumerate(good):
        f = tmp_path / f"{i}.json"
        write_config(x, f)
        r = subprocess.run([XRAY, "run", "-test", "-c", str(f)], capture_output=True, text=True, cwd=str(pathlib.Path(XRAY).parent))
        assert r.returncode == 0, (x["name"], r.stdout + r.stderr)

def test_pinned_cert_replaces_insecure():
    p = {x["name"]: x for x in loaded()[0]}["hy2 no sni"]
    assert not validate_profile(p)                  # accepted on import, pinned afterwards
    p = {**p, "pcs": "AA:" * 31 + "AA"}
    assert not validate_profile(p)
    tls = generate_config([p])["outbounds"][0]["streamSettings"]["tlsSettings"]
    assert tls["pinnedPeerCertSha256"] == "a" * 64 and "allowInsecure" not in tls
    with pytest.raises(ValueError):
        generate_config([{k: v for k, v in p.items() if k != "pcs"}])
