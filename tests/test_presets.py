"""Updatable bypass values: layers, allow-list checks, broken files, download + install, use in config and AUTO."""
import copy
import io
import json

import pytest

from app.core import autobypass, bypass, presets
from app.core.config_generator import generate_xray_config

BASE = {"name": "T", "type": "vless", "server": "1.1.1.1", "port": 443,
        "uuid": "123e4567-e89b-12d3-a456-426614174000", "network": "ws",
        "security": "tls", "sni": "a.workers.dev", "host": "a.workers.dev", "path": "/x"}

NEW_FM = {"tcp": [{"type": "fragment", "settings": {"packets": "tlshello", "lengths": ["0", "90", "1"],
                                                    "delays": ["0"], "maxSplit": "0"}}]}


def write(tmp_path, name, doc):
    p = tmp_path / name
    p.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def restore_real_presets():
    yield
    bypass.reload()


def test_without_files_the_builtin_values_are_used(tmp_path):
    r = presets.load(bypass.BUILTIN, tmp_path / "none1.json", tmp_path / "none2.json")
    assert r["presets"].keys() == bypass.BUILTIN.keys() and r["version"] == 1 and r["errors"] == []


def test_bundled_file_matches_builtin_values():
    doc, errs = presets.check_doc(json.loads(presets.BUNDLED_FILE.read_text(encoding="utf-8")))
    assert not errs
    for name, p in bypass.BUILTIN.items():
        assert doc["presets"][name]["finalmask"] == p["finalmask"]
        assert doc["presets"][name]["cipherSuites"] == p["cipherSuites"]


def test_user_layer_overrides_field_by_field(tmp_path):
    user = write(tmp_path, "u.json", {"version": 4, "presets": {"pattng": {"finalmask": NEW_FM}}})
    r = presets.load(bypass.BUILTIN, tmp_path / "none.json", user)
    p = r["presets"]["pattng"]
    assert p["finalmask"] == NEW_FM and r["version"] == 4
    assert p["cipherSuites"] == bypass.CIPHER_SUITES and p["label"] == bypass.BUILTIN["pattng"]["label"]
    assert r["presets"]["standard"] == bypass.BUILTIN["standard"]


def test_new_values_reach_the_xray_config(tmp_path):
    user = write(tmp_path, "u.json", {"version": 2, "presets": {"pattng": {"finalmask": NEW_FM}}})
    bypass.reload(tmp_path / "none.json", user)
    s = generate_xray_config({**BASE, "bypass": "pattng"})["outbounds"][0]["streamSettings"]
    assert s["finalmask"]["tcp"][0]["settings"]["lengths"] == ["0", "90", "1"]
    assert s["tlsSettings"]["fingerprint"] == "unsafe"


def test_config_does_not_share_the_preset_objects(tmp_path):
    s1 = generate_xray_config({**BASE, "bypass": "pattng"})["outbounds"][0]["streamSettings"]
    s1["finalmask"]["tcp"][0]["settings"]["lengths"].append("999")
    s2 = generate_xray_config({**BASE, "bypass": "pattng"})["outbounds"][0]["streamSettings"]
    assert "999" not in s2["finalmask"]["tcp"][0]["settings"]["lengths"]


def test_a_new_method_shows_up_in_menu_and_auto(tmp_path):
    extra = {"label": "Method 3", "fingerprint": "chrome", "finalmask": NEW_FM, "auto": True}
    user = write(tmp_path, "u.json", {"version": 2, "presets": {"m3": extra}})
    bypass.reload(tmp_path / "none.json", user)
    assert "m3" in bypass.PRESETS and bypass.PRESETS["m3"] == "Method 3"
    assert list(bypass.PRESETS)[0] == "off" and list(bypass.PRESETS)[-1] == "custom"
    assert bypass.auto_names() == ["pattng", "standard", "m3"]
    v = autobypass.variants({**BASE}, doh_urls=["https://dns.google/dns-query"])
    assert [x["bypass"] for x in v] == ["off", "pattng", "standard", "m3", "ech"]
    s = generate_xray_config({**BASE, "bypass": "m3"})["outbounds"][0]["streamSettings"]
    assert s["tlsSettings"]["fingerprint"] == "chrome" and "cipherSuites" not in s["tlsSettings"]


def test_a_method_without_auto_is_not_tried_by_auto(tmp_path):
    user = write(tmp_path, "u.json", {"version": 2, "presets": {"quiet": {"label": "Q", "finalmask": NEW_FM}}})
    bypass.reload(tmp_path / "none.json", user)
    assert "quiet" in bypass.PRESETS and "quiet" not in bypass.auto_names()


@pytest.mark.parametrize("bad, why", [
    ({"finalmask": NEW_FM, "script": "x"}, "unknown field"),
    ({"fingerprint": "evil"}, "fingerprint"),
    ({"cipherSuites": "tls_aes_128; rm -rf"}, "cipherSuites"),
    ({"finalmask": {"tcp": [{"type": "header-custom", "settings": {}}]}}, "mask type"),
    ({"finalmask": {"tcp": [{"type": "fragment", "settings": {"x": {"nested": 1}}}]}}, "setting"),
    ({"finalmask": {"icmp": [{"type": "fragment"}]}}, "network"),
    ({"finalmask": {"tcp": []}}, "list"),
    ({"auto": "yes"}, "auto"),
    ({"label": ""}, "label"),
])
def test_bad_presets_are_refused_with_a_reason(bad, why):
    doc, errs = presets.check_doc({"version": 1, "presets": {"good": {"label": "ok"}, "bad": bad}})
    assert "good" in doc["presets"] and "bad" not in doc["presets"]
    assert len(errs) == 1 and errs[0].startswith("bad:") and why in errs[0]


def test_reserved_and_badly_named_presets_are_refused():
    doc, errs = presets.check_doc({"version": 1, "presets": {"off": {}, "ech": {}, "custom": {}, "Bad Name": {}, "ok_1": {}}})
    assert list(doc["presets"]) == ["ok_1"] and len(errs) == 4


@pytest.mark.parametrize("raw", [[], "x", {"version": "3", "presets": {}}, {"version": 1}, {"version": True, "presets": {}},
                                 {"version": -1, "presets": {}}])
def test_malformed_documents_raise(raw):
    with pytest.raises(ValueError):
        presets.check_doc(raw)


def test_corrupt_file_falls_back_and_is_kept_as_bad(tmp_path):
    user = write(tmp_path, "u.json", "{ this is not json")
    r = presets.load(bypass.BUILTIN, tmp_path / "none.json", user)
    assert r["presets"].keys() == bypass.BUILTIN.keys() and r["errors"]
    assert (tmp_path / "u.json.bad").exists()


def test_a_file_with_one_bad_preset_keeps_the_good_ones(tmp_path):
    user = write(tmp_path, "u.json", {"version": 3, "presets": {
        "pattng": {"finalmask": NEW_FM}, "evil": {"fingerprint": "nope"}}})
    r = presets.load(bypass.BUILTIN, tmp_path / "none.json", user)
    assert r["presets"]["pattng"]["finalmask"] == NEW_FM and "evil" not in r["presets"] and len(r["errors"]) == 1


def test_unknown_method_name_is_an_error():
    with pytest.raises(ValueError):
        generate_xray_config({**BASE, "bypass": "does_not_exist"})


# ------------------------------------------------------------------ downloading
class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_net(monkeypatch, body, seen=None):
    class Opener:
        def __init__(self, proxy): self.proxy = proxy
        def open(self, req, timeout=0):
            if seen is not None: seen.append((req.full_url, self.proxy))
            if isinstance(body, Exception): raise body
            return _Resp(body if isinstance(body, bytes) else json.dumps(body).encode())
    monkeypatch.setattr(presets, "_opener", lambda proxy: Opener(proxy))


def test_update_installs_a_newer_file(tmp_path, monkeypatch):
    seen = []
    fake_net(monkeypatch, {"version": 5, "presets": {"pattng": {"finalmask": NEW_FM}}}, seen)
    user = tmp_path / "data" / "bypass_presets.json"
    status, doc, errs = presets.update(1, proxy="http://127.0.0.1:10809", user_file=user)
    assert status == "updated" and user.exists() and seen[0][0] == presets.DEFAULT_URL
    assert seen[0][1] == "http://127.0.0.1:10809"                      # through the tunnel first
    saved = json.loads(user.read_text(encoding="utf-8"))
    assert saved["version"] == 5 and saved["presets"]["pattng"]["finalmask"] == NEW_FM
    bypass.reload(tmp_path / "none.json", user)
    assert bypass.STATE["version"] == 5


def test_update_ignores_a_file_that_is_not_newer(tmp_path, monkeypatch):
    fake_net(monkeypatch, {"version": 3, "presets": {"pattng": {"finalmask": NEW_FM}}})
    user = tmp_path / "u.json"
    status, _, _ = presets.update(3, user_file=user)
    assert status == "current" and not user.exists()


def test_update_falls_back_to_a_direct_download(tmp_path, monkeypatch):
    seen = []
    class Opener:
        def __init__(self, proxy): self.proxy = proxy
        def open(self, req, timeout=0):
            seen.append(self.proxy)
            if self.proxy: raise OSError("tunnel is down")
            return _Resp(json.dumps({"version": 2, "presets": {"standard": {"label": "S2"}}}).encode())
    monkeypatch.setattr(presets, "_opener", lambda proxy: Opener(proxy))
    status, doc, _ = presets.update(1, proxy="http://127.0.0.1:1", user_file=tmp_path / "u.json")
    assert status == "updated" and seen == ["http://127.0.0.1:1", None]


def test_update_refuses_http_and_oversize_and_empty(tmp_path, monkeypatch):
    with pytest.raises(presets.PresetError):
        presets.fetch("http://example.com/p.json")
    fake_net(monkeypatch, b" " * (presets.MAX_BYTES + 10))
    with pytest.raises(presets.PresetError):
        presets.fetch()
    fake_net(monkeypatch, {"version": 9, "presets": {"x": {"fingerprint": "nope"}}})
    with pytest.raises(presets.PresetError):
        presets.fetch()
    fake_net(monkeypatch, b"<html>not json</html>")
    with pytest.raises(presets.PresetError):
        presets.fetch()
    fake_net(monkeypatch, OSError("offline"))
    with pytest.raises(presets.PresetError):
        presets.fetch()


def test_update_never_writes_the_unchecked_parts(tmp_path, monkeypatch):
    fake_net(monkeypatch, {"version": 2, "presets": {"pattng": {"finalmask": NEW_FM},
                                                     "evil": {"cipherSuites": "a b"}, "off": {"label": "x"}}})
    user = tmp_path / "u.json"
    status, doc, errs = presets.update(1, user_file=user)
    saved = json.loads(user.read_text(encoding="utf-8"))
    assert list(saved["presets"]) == ["pattng"] and len(errs) == 2


def test_auto_update_is_silent_and_rate_limited(tmp_path, monkeypatch):
    fake_net(monkeypatch, {"version": 7, "presets": {"standard": {"label": "S7"}}})
    user = tmp_path / "u.json"
    monkeypatch.setattr(presets, "_LAST", {"t": None})
    clock = [1000.0]
    r = presets.auto_update(1, now=lambda: clock[0], user_file=user)
    assert r[0] == "updated" and user.exists()
    assert presets.auto_update(1, now=lambda: clock[0] + 60, user_file=user) is None          # too soon
    assert presets.auto_update(1, now=lambda: clock[0] + 7 * 3600, user_file=user)[0] == "updated"


def test_auto_update_swallows_every_failure(tmp_path, monkeypatch):
    fake_net(monkeypatch, OSError("offline"))
    monkeypatch.setattr(presets, "_LAST", {"t": None})
    assert presets.auto_update(1, user_file=tmp_path / "u.json") is None
    assert not (tmp_path / "u.json").exists()


def test_shipped_file_has_whitedns_presets_and_all_pass_check():
    from app.core import presets
    raw = json.loads(presets.BUNDLED_FILE.read_text("utf-8"))
    doc, errs = presets.check_doc(raw)
    assert errs == []
    for n in range(1, 6):
        p = doc["presets"][f"wd{n}"]
        assert p["auto"] is True and p["finalmask"]["tcp"][0]["settings"]["packets"] == "tlshello"
