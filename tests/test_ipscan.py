import random, shutil, socket, ssl, subprocess, threading, ipaddress
import pytest
from app.core import ipscan

def test_sample_ips_in_ranges_and_distinct():
    ips = ipscan.sample_ips(ipscan.FALLBACK_RANGES, 200, random.Random(1))
    assert len(ips) == len(set(ips)) == 200
    nets = [ipaddress.ip_network(r) for r in ipscan.FALLBACK_RANGES]
    assert all(any(ipaddress.ip_address(i) in n for n in nets) for i in ips)

def test_parse_trace():
    assert ipscan.parse_trace("fl=1\ncolo=FRA\nloc=DE\n")["colo"] == "FRA"

def test_scan_target_and_cloudflare_detect():
    p = {"server": "1.2.3.4", "port": 443, "sni": "x.workers.dev", "security": "tls"}
    assert ipscan.scan_target(p) == (443, "x.workers.dev")
    assert ipscan.looks_cloudflare(p)
    assert not ipscan.looks_cloudflare({"port": 443, "security": "reality"})
    assert not ipscan.looks_cloudflare({"port": 1234, "security": "tls"})

@pytest.fixture
def tls_server(tmp_path):
    if not shutil.which("openssl"):
        pytest.skip("openssl missing")
    crt, key = tmp_path / "c.pem", tmp_path / "k.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt),
                    "-days", "1", "-subj", "/CN=test.example"], check=True, capture_output=True)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(crt, key)
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(8)
    state = {"status": "200 OK", "body": "fl=1\ncolo=PRG\nloc=DE\n", "hosts": []}
    def serve():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            try:
                s = ctx.wrap_socket(c, server_side=True)
                req = s.recv(4096).decode()
                state["hosts"].append([l for l in req.split("\r\n") if l.startswith("Host:")][0])
                s.sendall(f"HTTP/1.1 {state['status']}\r\nContent-Length: {len(state['body'])}\r\n\r\n{state['body']}".encode())
                s.close()
            except Exception:
                pass
    threading.Thread(target=serve, daemon=True).start()
    yield srv.getsockname()[1], state
    srv.close()

def test_probe_ok_sends_host(tls_server):
    port, st = tls_server
    ms, colo = ipscan.probe("127.0.0.1", port, "my.workers.dev")
    assert colo == "PRG" and ms >= 0
    assert st["hosts"] == ["Host: my.workers.dev"]

def test_probe_rejects_non_cloudflare_answer(tls_server):
    port, st = tls_server
    st["body"] = "hello"
    assert ipscan.probe("127.0.0.1", port, "a.b") is None
    st["status"], st["body"] = "403 Forbidden", "colo=X\n"
    assert ipscan.probe("127.0.0.1", port, "a.b") is None

def test_probe_closed_port_and_scan(tls_server):
    port, _ = tls_server
    dead = socket.socket(); dead.bind(("127.0.0.1", 0)); dp = dead.getsockname()[1]; dead.close()
    assert ipscan.probe("127.0.0.1", dp, "a.b", timeout=0.5) is None
    found = []
    n = ipscan.scan(["127.0.0.1"], port, "a.b", lambda ip, ms, colo: found.append((ip, colo)))
    assert n == 1 and found == [("127.0.0.1", "PRG")]
