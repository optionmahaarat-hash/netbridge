from app.core import autobypass
from app.utils import latency


def test_check_upload_ok_and_failures():
    ok, ms, d = latency.check_upload("p", post=lambda *a: 12)
    assert ok and ms == 12 and "50 KB" in d

    def stall(*a):
        raise TimeoutError("timed out")
    ok, ms, d = latency.check_upload("p", post=stall)
    assert not ok and ms == -1 and "timed out" in d


def test_post_sends_body_through_proxy(monkeypatch):
    seen = {}

    class R:
        def read(self, n): return b""
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class O:
        def open(self, req, timeout=None):
            seen["n"] = len(req.data); seen["m"] = req.get_method(); return R()

    monkeypatch.setattr(latency.urllib.request, "build_opener", lambda *a: O())
    latency._post("http://127.0.0.1:1", "https://x/__up", 5, 1234)
    assert seen == {"n": 1234, "m": "POST"}


def test_post_http_error_counts_as_delivered(monkeypatch):
    import urllib.error

    class O:
        def open(self, req, timeout=None):
            raise urllib.error.HTTPError("u", 400, "bad", {}, None)

    monkeypatch.setattr(latency.urllib.request, "build_opener", lambda *a: O())
    assert latency._post("p", "https://x", 5, 10) >= 0


def _sites(monkeypatch, good):
    monkeypatch.setattr(latency, "check_sites", lambda *a, **k: [("YouTube", good, 100, "HTTP 204")])


def test_verify_rejects_upload_limited(monkeypatch):
    _sites(monkeypatch, True)
    autobypass.UPLOAD_LIMITED["n"] = 0
    assert autobypass._verify(1, upload=lambda p, t: (False, -1, "timed out")) is None
    assert autobypass.UPLOAD_LIMITED["n"] == 1
    assert autobypass._verify(1, upload=lambda p, t: (True, 30, "ok")) == 100


def test_verify_sites_fail_skips_upload(monkeypatch):
    _sites(monkeypatch, False)
    called = []
    assert autobypass._verify(1, upload=lambda p, t: called.append(1) or (True, 1, "")) is None
    assert called == []
