import json, pathlib, shutil, socket, struct, subprocess, threading, time, http.server
import pytest
from app.core.routing import (build_dns, build_routing, sdns_active, parse_dns_server,
                              SERVICE_PRESETS, SDNS_PRESETS)
from app.core.config_generator import generate_config
from app.utils import dnscheck

VL = {"name": "A", "type": "vless", "server": "1.1.1.1", "port": 443,
      "uuid": "123e4567-e89b-12d3-a456-426614174000", "network": "ws",
      "security": "tls", "sni": "a.workers.dev", "path": "/x"}
XRAY = shutil.which("xray") or "/tmp/xr/xray"
HAVE_XRAY = pathlib.Path(XRAY).exists()

def test_parse_dns_server():
    assert parse_dns_server("178.22.122.100") == ("178.22.122.100", 53)
    assert parse_dns_server(" 1.2.3.4:5353 ") == ("1.2.3.4", 5353)
    for bad in ("shecan.ir", "1.2.3.4:99999", "999.1.1.1"):
        with pytest.raises(ValueError): parse_dns_server(bad)

def test_inactive_without_server_or_sites():
    assert sdns_active({}) is None and sdns_active({"sdns_server": "1.1.1.1"}) is None
    assert sdns_active({"sdns_sites": ["a.com"]}) is None
    assert build_dns({}) is None
    assert "sdns" not in [o["tag"] for o in generate_config([VL], {"routing": {}})["outbounds"]]

def test_config_has_dns_outbound_and_rules():
    c = generate_config([VL], {"routing": {"sdns_server": "9.9.9.9", "sdns_sites": ["docker.com"], "pin_sites": ["x.com"]}})
    assert c["dns"]["servers"][0]["domains"] == ["domain:docker.com"]
    sd = [o for o in c["outbounds"] if o["tag"] == "sdns"][0]
    assert sd["settings"]["domainStrategy"] == "UseIPv4"
    r = c["routing"]["rules"]
    assert r[0] == {"type": "field", "ip": ["9.9.9.9"], "outboundTag": "direct"}   # DNS packets leave directly
    assert {"type": "field", "domain": ["domain:docker.com"], "outboundTag": "sdns"} in r

def test_presets_are_valid_entries():
    from app.core.routing import classify
    for name, doms in SERVICE_PRESETS.items():
        assert doms and all(classify(d)[0] == "domain" for d in doms), name
    for ip in SDNS_PRESETS.values(): parse_dns_server(ip)

# ---- fake DNS server (answers A = 127.0.0.1 for names ending .test, NXDOMAIN otherwise)
def fake_dns(answer_ip="127.0.0.1"):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1", 0))
    def loop():
        while True:
            try: data, addr = s.recvfrom(512)
            except OSError: return
            qid = data[:2]; pos = 12; labels = []
            while data[pos]: labels.append(data[pos + 1:pos + 1 + data[pos]].decode()); pos += data[pos] + 1
            qend = pos + 5; name = ".".join(labels)
            if name.endswith(".test") and data[qend - 4:qend - 2] == b"\x00\x01":
                resp = qid + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + data[12:qend] + \
                       b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + socket.inet_aton(answer_ip)
            else:
                resp = qid + b"\x81\x83\x00\x01\x00\x00\x00\x00\x00\x00" + data[12:qend]
            s.sendto(resp, addr)
    threading.Thread(target=loop, daemon=True).start()
    return s

def test_dnscheck_against_fake_server():
    s = fake_dns(); port = s.getsockname()[1]
    assert dnscheck.resolve("docker.test", "127.0.0.1", port) == (0, ["127.0.0.1"])
    assert dnscheck.resolve("nope.example", "127.0.0.1", port)[0] == 3
    ok, msg = dnscheck.describe("docker.test", "127.0.0.1", port); assert not ok and "private" in msg
    s2 = fake_dns("8.8.4.4"); ok, msg = dnscheck.describe("a.test", "127.0.0.1", s2.getsockname()[1]); assert ok and "8.8.4.4" in msg
    ok, msg = dnscheck.describe("a.test", "127.0.0.1", 9); assert not ok
    s.close(); s2.close()

def free_port():
    with socket.socket() as t: t.bind(("127.0.0.1", 0)); return t.getsockname()[1]

@pytest.mark.skipif(not HAVE_XRAY, reason="no xray binary")
def test_real_xray_resolves_listed_site_with_smart_dns(tmp_path):
    """End to end: listed site -> Smart DNS -> direct. Unlisted site -> tunnel (which is dead here)."""
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"REACHED-DIRECT")
        def log_message(self, *a): pass
    web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); wport = web.server_address[1]
    threading.Thread(target=web.serve_forever, daemon=True).start()
    dns = fake_dns(); dport = dns.getsockname()[1]
    hport = free_port()
    cfg = generate_config([VL], {"routing": {"lan": False, "sdns_server": f"127.0.0.1:{dport}",
                                              "sdns_sites": ["sanctioned.test"]}},
                          socks_port=0, http_port=hport, loglevel="warning")
    f = tmp_path / "c.json"; f.write_text(json.dumps(cfg))
    p = subprocess.Popen([XRAY, "run", "-c", str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            with socket.socket() as t:
                if t.connect_ex(("127.0.0.1", hport)) == 0: break
            time.sleep(0.1)
        listed = subprocess.run(["curl", "-s", "-m", "6", "-x", f"http://127.0.0.1:{hport}",
                                 f"http://sanctioned.test:{wport}/"], capture_output=True, text=True)
        assert listed.stdout == "REACHED-DIRECT", (listed.stdout, listed.stderr)
        other = subprocess.run(["curl", "-s", "-m", "4", "-x", f"http://127.0.0.1:{hport}",
                                f"http://other.test:{wport}/"], capture_output=True, text=True)
        assert other.stdout != "REACHED-DIRECT"          # not listed -> goes to the (dead) tunnel
    finally:
        p.terminate(); web.shutdown(); dns.close()
