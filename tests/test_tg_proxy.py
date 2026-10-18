import json
import re

import pytest

from app.core import tg_proxy
from app.core.cf_deploy import DeployError, multipart

TOKEN = "a" * 40
SRC = "export default { fetch: (r, env) => env.SECRET + env.BOOT };"


class Fake:
    def __init__(self, subdomain="me"):
        self.calls, self.subdomain = [], subdomain

    def __call__(self, method, path, token, body=None, content_type="application/json", timeout=30, proxy=None):
        self.calls.append((method, path, body, content_type))
        if path == "/user/tokens/verify":
            return {"status": "active"}
        if path == "/accounts":
            return [{"id": "acc1"}]
        if path == "/accounts/acc1/workers/subdomain" and method == "GET":
            return {"subdomain": self.subdomain} if self.subdomain else {}
        return {}


def test_secrets_have_the_documented_shape():
    assert re.fullmatch(r"[0-9a-f]{32}", tg_proxy.gen_secret())
    assert re.fullmatch(r"[0-9a-f]{48}", tg_proxy.gen_boot())
    assert tg_proxy.gen_secret() != tg_proxy.gen_secret()


def test_link_format():
    assert tg_proxy.link("tg.example.com", "abc") == "https://t.me/webproxy?server=tg.example.com&secret=abc"


def test_multipart_carries_secret_bindings():
    body, ctype = multipart(SRC, [{"type": "secret_text", "name": "SECRET", "text": "s"}])
    text = body.decode()
    meta = json.loads(text.split("\r\n\r\n", 1)[1].split("\r\n--", 1)[0])
    assert meta["bindings"] == [{"type": "secret_text", "name": "SECRET", "text": "s"}]
    assert "boundary=" in ctype and SRC in text


def test_multipart_without_bindings_is_unchanged():
    body, _ = multipart(SRC)
    assert b"bindings" not in body


def test_deploy_workers_dev_only():
    f = Fake()
    r = tg_proxy.deploy(TOKEN, SRC, call=f)
    assert r["domain"] is None and r["server"] == r["workers_host"]
    assert r["workers_host"].endswith(".me.workers.dev")
    assert r["link"] == f"https://t.me/webproxy?server={r['server']}&secret={r['secret']}"
    put = [c for c in f.calls if c[0] == "PUT" and "/workers/scripts/" in c[1]][0]
    assert r["secret"] in put[2].decode() and r["boot"] in put[2].decode()
    assert not any("/workers/domains" in c[1] for c in f.calls)


def test_deploy_with_custom_domain():
    f = Fake()
    r = tg_proxy.deploy(TOKEN, SRC, zone=("z1", "Example.COM"), label="TG", call=f)
    assert r["domain"] == "tg.example.com" and r["server"] == "tg.example.com"
    c = [c for c in f.calls if c[1] == "/accounts/acc1/workers/domains"][0]
    assert c[0] == "PUT" and c[2] == {"hostname": "tg.example.com", "service": r["name"], "zone_id": "z1", "environment": "production"}


def test_apex_domain_when_label_is_empty():
    assert tg_proxy.hostname("", "example.com") == "example.com"
    assert tg_proxy.hostname("@", "example.com") == "example.com"


def test_creates_workers_subdomain_when_missing():
    f = Fake(subdomain=None)
    tg_proxy.deploy(TOKEN, SRC, call=f)
    assert any(c[0] == "PUT" and c[1] == "/accounts/acc1/workers/subdomain" for c in f.calls)


@pytest.mark.parametrize("label", ["a b", "-x", "x-", "a/b", "a.b", "A_B"])
def test_bad_labels_are_refused(label):
    with pytest.raises(DeployError):
        tg_proxy.hostname(label, "example.com")


def test_bad_token_and_name():
    with pytest.raises(DeployError):
        tg_proxy.deploy("short", SRC, call=Fake())
    with pytest.raises(DeployError):
        tg_proxy.deploy(TOKEN, SRC, name="Bad Name", call=Fake())


def test_no_account():
    def call(method, path, token, *a, **k):
        return [] if path == "/accounts" else {}
    with pytest.raises(DeployError):
        tg_proxy.deploy(TOKEN, SRC, call=call)


def test_list_zones():
    def call(method, path, token, *a, **k):
        assert path.startswith("/zones")
        return [{"id": "1", "name": "a.com"}, {"id": "2"}, {"name": "x"}]
    assert tg_proxy.list_zones(TOKEN, call=call) == [("1", "a.com")]


def test_fetch_source_rejects_wrong_file(monkeypatch):
    class R:
        def __init__(self, data): self.data = data
        def read(self, n=-1): return self.data[:n]
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class O:
        def __init__(self, data): self.data = data
        def open(self, req, timeout=0): return R(self.data)
    monkeypatch.setattr(tg_proxy.urllib.request, "build_opener", lambda *h: O(b"<html>not it</html>"))
    with pytest.raises(DeployError):
        tg_proxy.fetch_source()
    monkeypatch.setattr(tg_proxy.urllib.request, "build_opener", lambda *h: O(SRC.encode()))
    assert tg_proxy.fetch_source() == SRC


def test_health_parsing(monkeypatch):
    class R:
        def __init__(self, data): self.data = data
        def read(self, n=-1): return self.data
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class O:
        def __init__(self, data): self.data = data
        def open(self, req, timeout=0): return R(self.data)
    monkeypatch.setattr(tg_proxy.urllib.request, "build_opener", lambda *h: O(b'{"ok":true}'))
    assert tg_proxy.health("x.example.com")[0] is True
    monkeypatch.setattr(tg_proxy.urllib.request, "build_opener", lambda *h: O(b"nope"))
    assert tg_proxy.health("x.example.com")[0] is False
