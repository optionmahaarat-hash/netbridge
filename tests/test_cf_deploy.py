import json
import pytest
from app.core import cf_deploy as cd
from app.utils.validator import validate_profile

TOKEN = "A" * 40


def fake(log, subdomain="me"):
    def call(method, path, token, body=None, content_type="application/json", **kw):
        log.append((method, path, body, content_type))
        if path == "/user/tokens/verify": return {"status": "active"}
        if path == "/accounts": return [{"id": "acc1"}]
        if path.endswith("/workers/subdomain") and method == "GET": return {"subdomain": subdomain}
        return {}
    return call


def test_deploy_builds_profile_and_uploads_uuid():
    log = []
    p = cd.deploy(TOKEN, name="nb-test", uuid_str="11111111-2222-3333-4444-555555555555", call=fake(log))
    assert p["server"] == "nb-test.me.workers.dev" and p["sni"] == p["host"] == p["server"]
    assert validate_profile(p) == []
    put = next(x for x in log if x[0] == "PUT" and "scripts" in x[1])
    assert b"11111111-2222-3333-4444-555555555555" in put[2] and b"__UUID__" not in put[2]
    assert "multipart/form-data" in put[3]
    assert any(x[1].endswith("/nb-test/subdomain") and x[2]["enabled"] for x in log)


def test_creates_subdomain_when_missing():
    log = []
    cd.deploy(TOKEN, call=fake(log, subdomain=None))
    assert any(x[0] == "PUT" and x[1].endswith("/workers/subdomain") for x in log)


def test_bad_inputs():
    with pytest.raises(cd.DeployError): cd.deploy("short", call=fake([]))
    with pytest.raises(cd.DeployError): cd.deploy(TOKEN, name="Bad Name", call=fake([]))
    with pytest.raises(cd.DeployError): cd.worker_source("x'; alert(1)//")


def test_no_account():
    def call(m, p, t, *a, **k): return {} if "verify" in p else []
    with pytest.raises(cd.DeployError): cd.deploy(TOKEN, call=call)


def test_worker_source_has_no_leftover():
    s = cd.worker_source("11111111-2222-3333-4444-555555555555")
    assert "__UUID__" not in s and "cloudflare:sockets" in s


def test_android_copy_of_the_worker_is_identical():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    assert (root / "android/app/src/main/assets/vless_worker.js").read_text(encoding="utf-8") == (root / "assets/worker/vless_worker.js").read_text(encoding="utf-8")
