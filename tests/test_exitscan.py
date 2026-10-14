import json, pathlib, shutil, socket, subprocess, threading, time, http.server
import pytest
from app.core import exitscan
from app.utils.leakcheck import _p_ipapi

XRAY = shutil.which("xray") or "/tmp/xr/xray"
pytestmark = pytest.mark.skipif(not pathlib.Path(XRAY).exists(), reason="no xray binary")
UUID = "123e4567-e89b-12d3-a456-426614174000"

def free_port():
    with socket.socket() as t: t.bind(("127.0.0.1", 0)); return t.getsockname()[1]

def test_is_workers_and_describe():
    assert exitscan.is_workers({"sni": "a.b.workers.dev"}) and exitscan.is_workers({"server": "x.pages.dev"})
    assert not exitscan.is_workers({"sni": "example.com", "server": "1.2.3.4"})
    assert "CLOUDFLARE" in exitscan.describe({"cc": "DE", "ip": "1.1.1.1", "org": "Cloudflare WARP", "cloudflare": True})
    assert "no answer" in exitscan.describe(None)

def test_probe_exit_through_real_xray(tmp_path):
    body = {"v": json.dumps({"status": "success", "query": "9.9.9.9", "countryCode": "FI",
                             "timezone": "Europe/Helsinki", "org": "Hetzner Online GmbH", "hosting": True})}
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_GET(self):
            b = body["v"].encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def log_message(self, *a): pass
    web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); wport = web.server_address[1]
    threading.Thread(target=web.serve_forever, daemon=True).start()
    sport = free_port()
    srv = {"log": {"loglevel": "none"},
           "inbounds": [{"listen": "127.0.0.1", "port": sport, "protocol": "vless",
                         "settings": {"clients": [{"id": UUID}], "decryption": "none"}}],
           "outbounds": [{"protocol": "freedom", "settings": {"finalRules": [{"action": "allow"}]}}]}
    f = tmp_path / "s.json"; f.write_text(json.dumps(srv))
    sp = subprocess.Popen([XRAY, "run", "-c", str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            with socket.socket() as t:
                if t.connect_ex(("127.0.0.1", sport)) == 0: break
            time.sleep(0.1)
        prof = {"name": "t", "type": "vless", "server": "127.0.0.1", "port": sport, "uuid": UUID, "network": "tcp", "security": ""}
        src = [(f"http://127.0.0.1:{wport}/json", _p_ipapi)]
        r = exitscan.probe_exit(XRAY, prof, free_port(), sources=src, timeout=8)
        assert r and r["cc"] == "FI" and r["hosting"] is True and r["cloudflare"] is False and r["ip"] == "9.9.9.9"
        body["v"] = json.dumps({"status": "success", "query": "104.28.1.1", "countryCode": "DE", "org": "Cloudflare WARP"})
        assert exitscan.probe_exit(XRAY, prof, free_port(), sources=src, timeout=8)["cloudflare"] is True
        # scan_many: one alive, one dead profile
        dead = {**prof, "port": free_port()}
        got = {}
        exitscan.scan_many(XRAY, [("ok", prof), ("dead", dead)], lambda k, i: got.__setitem__(k, i), workers=2, sources=src, timeout=3)
        assert got["ok"] and got["ok"]["cc"] == "DE" and got["dead"] is None
    finally:
        sp.terminate(); web.shutdown()


def test_check_site_detects_google_style_block():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/blocked":
                self.send_response(302); self.send_header("Location", "/?location=unsupported"); self.end_headers()
            elif self.path == "/text":
                self.send_response(200); self.end_headers(); self.wfile.write(b"Gemini isn't available in your country yet")
            else:
                self.send_response(200); self.end_headers(); self.wfile.write(b"welcome")
        def log_message(self, *a): pass
    web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); port = web.server_address[1]
    threading.Thread(target=web.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        assert exitscan.check_site(base + "/app") == "ok"
        assert exitscan.check_site(base + "/blocked") == "blocked"
        assert exitscan.check_site(base + "/text") == "blocked"
        assert exitscan.check_site("http://127.0.0.1:9/") == "error"
    finally:
        web.shutdown()
    assert "NotebookLM:BLOCKED" in exitscan.describe({"cc": "DE", "ip": "1.1.1.1", "org": "x", "checks": {"NotebookLM": "blocked", "Gemini": "ok"}})


def test_check_site_reports_timeout_and_describe_words():
    import socket as _s
    srv = _s.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)           # accepts but never answers
    try:
        assert exitscan.check_site(f"http://127.0.0.1:{srv.getsockname()[1]}/", timeout=1) == "timeout"
    finally:
        srv.close()
    d = exitscan.describe({"cc": "FR", "ip": "1.1.1.1", "org": "OVH", "checks": {"NotebookLM": "timeout", "Gemini": "tls-error", "AI Studio": "error"}})
    assert "NotebookLM:TIMEOUT" in d and "Gemini:TLS-ERR" in d and "AI Studio:ERR" in d
