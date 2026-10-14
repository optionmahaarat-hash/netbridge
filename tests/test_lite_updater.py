import base64, http.server, json, socketserver, threading, zipfile
from pathlib import Path
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.lite import updater
from app.lite.updater import UpdateError
from tools.make_release import build


def keypair(tmp):
    k = Ed25519PrivateKey.generate()
    priv = tmp / "priv.key"
    priv.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return k.public_key(), priv


def fake_dist(tmp, version_marker="v2"):
    d = tmp / "dist"; (d / "_internal").mkdir(parents=True, exist_ok=True)
    (d / "NetBridgeLite.exe").write_bytes(b"EXE" + version_marker.encode())
    (d / "_internal" / "lib.dll").write_bytes(b"dll")
    (d / "data").mkdir(exist_ok=True); (d / "data" / "profiles.json").write_text("SECRET")   # must never be shipped
    return d


@pytest.fixture
def server(tmp_path):
    pub, priv = keypair(tmp_path)
    rel = tmp_path / "release"
    zp, m = build(fake_dist(tmp_path), rel, "نکته", "note", key_path=priv, version="0.2.0")
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(rel), **k)
    handler.log_message = lambda *a: None
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield pub, priv, rel, f"http://127.0.0.1:{srv.server_address[1]}/latest.json"
    srv.shutdown()


def test_version_compare():
    assert updater.is_newer("0.10.0", "0.9.5") and updater.is_newer("1.0.0", "0.99.9")
    assert not updater.is_newer("0.1.0", "0.1.0") and not updater.is_newer("0.1.0-beta", "0.1.1")


def test_release_never_contains_user_data(server):
    _, _, rel, _ = server
    names = zipfile.ZipFile(next(rel.glob("*.zip"))).namelist()
    assert "NetBridgeLite.exe" in names and not any(n.startswith("data/") for n in names)


def test_check_download_stage_happy_path(server, tmp_path):
    pub, _, _, url = server
    assert updater.check("0.1.0", [url], pub)["version"] == "0.2.0"
    assert updater.check("0.2.0", [url], pub) is None                      # already current
    m = updater.check("0.1.0", [url], pub)
    seen = []
    z = updater.download(m, tmp_path / "dl", progress=seen.append)
    assert seen and seen[-1] == 100
    root = updater.stage(z, tmp_path / "stage", "NetBridgeLite.exe")
    assert (root / "NetBridgeLite.exe").exists() and (root / "_internal" / "lib.dll").exists()


def test_wrong_key_is_refused(server, tmp_path):
    _, _, _, url = server
    other, _ = keypair(tmp_path)
    with pytest.raises(UpdateError, match="signature"):
        updater.check("0.1.0", [url], other)


@pytest.mark.parametrize("field,value", [("version", "9.9.9"), ("sha256", "0" * 64), ("size", 1), ("url", "evil.zip")])
def test_tampered_manifest_is_refused(server, field, value):
    pub, _, rel, _ = server
    m = json.loads((rel / "latest.json").read_text()); m[field] = value
    with pytest.raises(UpdateError, match="signature"):
        updater.verify_manifest(m, pub)


def test_swapped_zip_is_refused_by_hash(server, tmp_path):
    pub, _, rel, url = server
    m = updater.check("0.1.0", [url], pub)
    z = next(rel.glob("*.zip")); data = bytearray(z.read_bytes()); data[100] ^= 0xFF; z.write_bytes(bytes(data))
    with pytest.raises(UpdateError, match="hash"):
        updater.download(m, tmp_path / "dl")
    assert not list((tmp_path / "dl").glob("*.zip"))                        # damaged file is deleted


def test_zip_slip_and_missing_exe_are_refused(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("NetBridgeLite.exe", "x"); z.writestr("../evil.txt", "x")
    with pytest.raises(UpdateError, match="unsafe"):
        updater.stage(bad, tmp_path / "s1", "NetBridgeLite.exe")
    assert not (tmp_path / "evil.txt").exists()
    noexe = tmp_path / "noexe.zip"
    with zipfile.ZipFile(noexe, "w") as z: z.writestr("readme.txt", "x")
    with pytest.raises(UpdateError, match="not inside"):
        updater.stage(noexe, tmp_path / "s2", "NetBridgeLite.exe")


def test_unreachable_url_gives_clear_error():
    with pytest.raises(UpdateError):
        updater.fetch_manifest(["http://127.0.0.1:9/latest.json"], timeout=2)


def test_apply_script_keeps_data_and_restarts():
    s = updater.apply_script(r"C:\Program Files (x86)\NB", r"C:\Program Files (x86)\NB\updates\staging", "NetBridgeLite.exe", r"C:\x\a.zip")
    assert "/XD data updates" in s and 'start "" "%APP%\\%EXE%"' in s
    assert "if errorlevel 1 goto copy" in s and "(" not in s.split(":wait")[1].split(":copy")[0]   # no ( ) blocks: paths with (x86) are safe
    assert r"C:\Program Files (x86)\NB" in s and "update_failed.txt" in s
