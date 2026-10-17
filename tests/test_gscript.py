import base64, io, json, socket, ssl
import pytest
from app.core import gscript as g

KEY = "abcdEFGH1234"
URL = "https://script.google.com/macros/s/AKfycbxABCDEFGHIJKLMNOP/exec"


def test_code_gs_gets_the_key_and_rejects_bad_keys():
    assert f"'{KEY}'" in g.code_gs(KEY) and "__AUTH_KEY__" not in g.code_gs(KEY)
    for bad in ("", "short", "has space 12345", "q'uote12345"):
        with pytest.raises(g.GScriptError):
            g.code_gs(bad)
    assert len(g.new_key()) >= 20


def test_settings_validation():
    assert g.check_settings(URL, KEY)["front"] == "www.google.com"
    for u in ("http://script.google.com/macros/s/AKfycbxABCDEFGHIJKLMNOP/exec", "https://evil.com/macros/s/AKfycbxABCDEFGHIJKLMNOP/exec",
              "https://script.google.com/macros/s/AKfycbxABCDEFGHIJKLMNOP/dev", ""):
        with pytest.raises(g.GScriptError):
            g.check_settings(u, KEY)
    with pytest.raises(g.GScriptError):
        g.check_settings(URL, KEY, google_ip="not-an-ip")
    assert g.check_settings(URL, KEY, "216.239.38.120")["google_ip"] == "216.239.38.120"


def test_payload_and_reply():
    p = json.loads(g.build_payload(KEY, "POST", "https://a.b/c", {"Host": "a.b", "Accept-Encoding": "gzip", "X-A": "1"}, b"hi"))
    assert p["k"] == KEY and p["h"] == {"X-A": "1"} and base64.b64decode(p["b"]) == b"hi"
    raw = json.dumps({"s": 200, "h": {"Content-Type": "text/plain", "Set-Cookie": ["a=1", "b=2"], "Content-Encoding": "gzip"},
                      "b": base64.b64encode(b"data").decode()}).encode()
    s, hs, body = g.parse_reply(raw)
    assert s == 200 and body == b"data" and ("Set-Cookie", "b=2") in hs and all(k != "Content-Encoding" for k, _ in hs)
    with pytest.raises(g.GScriptError, match="secret key"):
        g.parse_reply(b'{"e":"auth"}')
    with pytest.raises(g.GScriptError, match="JSON"):
        g.parse_reply(b"<html>")


def test_read_request_plain_and_chunked():
    r = g.read_request(io.BytesIO(b"POST /x?y=1 HTTP/1.1\r\nHost: h\r\nContent-Length: 3\r\n\r\nabcGET / HTTP/1.1\r\n\r\n"))
    assert r[0] == "POST" and r[1] == "/x?y=1" and r[3] == b"abc"
    c = g.read_request(io.BytesIO(b"POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n"))
    assert c[3] == b"abcde"
    assert g.read_request(io.BytesIO(b"")) is None
    with pytest.raises(g.GScriptError):
        g.read_request(io.BytesIO(b"POST / HTTP/1.1\r\nContent-Length: 999999999\r\n\r\n"))


def test_full_url_and_response_bytes():
    assert g.full_url("https", "x.com", 443, "/p", {"Host": "x.com"}) == "https://x.com/p"
    assert g.full_url("http", "x.com", 8080, "/p", {}) == "http://x.com:8080/p"
    assert g.full_url("http", "x.com", 80, "http://y.com/z", {}) == "http://y.com/z"
    out = g.response_bytes(404, [("A", "b")], b"zz")
    assert out.startswith(b"HTTP/1.1 404 Not Found\r\nA: b\r\n") and out.endswith(b"\r\n\r\nzz") and b"Content-Length: 2" in out


class FakeRelay:
    def __init__(self): self.calls = []
    def fetch(self, method, url, headers=None, body=b""):
        self.calls.append((method, url, body))
        return 200, [("Content-Type", "text/plain")], b"hello " + url.encode()


def _socks(port, host, dport):
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(b"\x05\x01\x00"); assert s.recv(2) == b"\x05\x00"
    s.sendall(b"\x05\x01\x00\x03" + bytes([len(host)]) + host.encode() + dport.to_bytes(2, "big"))
    return s, s.recv(10)


def test_end_to_end_https_and_http_through_local_server(tmp_path):
    srv = g.GScriptServer(FakeRelay(), tmp_path, port=0)
    srv.sock = None
    # pick a free port
    with socket.socket() as t:
        t.bind(("127.0.0.1", 0)); srv.port = t.getsockname()[1]
    srv.start()
    try:
        ca = str(tmp_path / "ca.pem")
        ctx = ssl.create_default_context(cafile=ca)
        s, reply = _socks(srv.port, "example.test", 443)
        assert reply[1] == 0
        tls = ctx.wrap_socket(s, server_hostname="example.test")            # trusted only because of our local CA
        tls.sendall(b"POST /a HTTP/1.1\r\nHost: example.test\r\nContent-Length: 2\r\n\r\nhi")
        f = tls.makefile("rb")
        assert f.readline().startswith(b"HTTP/1.1 200")
        hdr = {}
        for line in iter(f.readline, b"\r\n"):
            k, v = line.decode().split(":", 1); hdr[k.lower()] = v.strip()
        assert f.read(int(hdr["content-length"])) == b"hello https://example.test/a"
        tls.sendall(b"GET /b HTTP/1.1\r\nHost: example.test\r\n\r\n")      # keep-alive: a second request on the same connection
        assert f.readline().startswith(b"HTTP/1.1 200")
        tls.close()
        s, reply = _socks(srv.port, "plain.test", 80)
        s.sendall(b"GET /x HTTP/1.1\r\nHost: plain.test\r\n\r\n")
        assert b"hello http://plain.test/x" in s.recv(4096)
        s.close()
        s, reply = _socks(srv.port, "example.test", 25)                     # not web traffic: refused
        assert reply[1] == 5
        assert [c[1] for c in srv.relay.calls][:2] == ["https://example.test/a", "https://example.test/b"]
    finally:
        srv.stop()


def test_ca_is_created_once_and_profile_marked(tmp_path):
    a = g.ensure_ca(tmp_path); b = g.ensure_ca(tmp_path)
    assert a == b and a[0].read_bytes().startswith(b"-----BEGIN CERTIFICATE")
    p = g.local_profile(1830)
    assert g.is_gscript(p) and p["type"] == "socks" and p["port"] == 1830 and not g.is_gscript({"engine": "aether"})
    assert g.install_ca_args("x.pem")[:4] == ["certutil", "-user", "-addstore", "Root"]
