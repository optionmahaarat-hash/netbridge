import hashlib
import io
import json
import socket
import threading
import zipfile

import pytest

from app.core import aether, autobypass
from app.core.config_generator import generate_config


def zip_with(name="aether-windows-x86_64/aether.exe", data=b"MZ-fake"):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, data)
        z.writestr("run-aether.bat", "x")
    return b.getvalue()


def release(tag="v2.3.0", names=("aether-windows-x86_64.zip", "aether-windows-x86_64.zip.sha256", "aether-linux-arm64.tar.gz")):
    return {"tag_name": tag, "assets": [{"name": n, "browser_download_url": aether.DOWNLOAD_PREFIX + tag + "/" + n} for n in names]}


# ---------------------------------------------------------------- picking / parsing
def test_pick_asset_finds_windows_zip_and_checksum():
    a, s = aether.pick_asset(release())
    assert a["name"] == "aether-windows-x86_64.zip" and s["name"].endswith(".sha256")


def test_pick_asset_prefers_x64_and_skips_arm():
    r = release(names=("aether-windows-arm64.zip", "aether-windows.zip", "aether-windows-x86_64.zip", "aether-windows-x86_64.zip.sha256"))
    assert aether.pick_asset(r)[0]["name"] == "aether-windows-x86_64.zip"
    with pytest.raises(aether.AetherError):
        aether.pick_asset(release(names=("aether-linux-arm64.tar.gz",)))


def test_pick_asset_accepts_shared_sums_file():
    r = release(names=("aether-windows-x86_64.zip", "SHA256SUMS"))
    assert aether.pick_asset(r)[1]["name"] == "SHA256SUMS"


def test_parse_sha_forms():
    h = "a" * 64
    assert aether.parse_sha(h + "\n", "x.zip") == h
    assert aether.parse_sha(f"{h}  x.zip\n", "x.zip") == h
    assert aether.parse_sha(f"{'b'*64}  other.zip\n{h} *x.zip\n", "X.zip") == h
    assert aether.parse_sha(f"{'b'*64}  other.zip\n{h}  y.zip\n", "x.zip") is None
    assert aether.parse_sha("garbage", "x.zip") is None


def test_extract_exe_only_takes_aether_exe():
    assert aether.extract_exe(zip_with()) == b"MZ-fake"
    with pytest.raises(aether.AetherError):
        aether.extract_exe(zip_with(name="evil.exe"))
    with pytest.raises(aether.AetherError):
        aether.extract_exe(b"not a zip")


# ---------------------------------------------------------------- download_core
def fake_fetch(blob, sha=None, rel=None, calls=None):
    rel = rel or release()
    sha = sha if sha is not None else hashlib.sha256(blob).hexdigest() + "  aether-windows-x86_64.zip\n"

    def fetch(url, timeout=30, proxy=None):
        if calls is not None:
            calls.append(url)
        if url == aether.API_LATEST:
            return json.dumps(rel).encode()
        if url.endswith(".sha256"):
            return sha.encode()
        return blob
    return fetch


def test_download_installs_when_checksum_matches(tmp_path):
    blob = zip_with()
    path, tag = aether.download_core(tmp_path / "core", fetch=fake_fetch(blob))
    assert path.read_bytes() == b"MZ-fake" and tag == "v2.3.0"
    assert "AGPL" in (tmp_path / "core" / "VERSION.txt").read_text()
    assert aether.installed(tmp_path / "core")


def test_download_refuses_bad_checksum_and_installs_nothing(tmp_path):
    with pytest.raises(aether.AetherError, match="SHA-256"):
        aether.download_core(tmp_path / "core", fetch=fake_fetch(zip_with(), sha="0" * 64 + "  aether-windows-x86_64.zip"))
    assert not aether.installed(tmp_path / "core")


def test_download_refuses_without_checksum_file(tmp_path):
    r = release(names=("aether-windows-x86_64.zip",))
    with pytest.raises(aether.AetherError, match="SHA-256"):
        aether.download_core(tmp_path / "core", fetch=fake_fetch(zip_with(), rel=r))


def test_download_refuses_foreign_address(tmp_path):
    r = release()
    r["assets"][0]["browser_download_url"] = "https://evil.example/aether-windows-x86_64.zip"
    with pytest.raises(aether.AetherError, match="official"):
        aether.download_core(tmp_path / "core", fetch=fake_fetch(zip_with(), rel=r))


# ---------------------------------------------------------------- running
def test_build_args_flags_and_modes():
    a = aether.build_args("a.exe", 1900, "h3", config="c.toml")
    assert a[:3] == ["a.exe", "--bind", "127.0.0.1:1900"] and "--masque" in a and "--h2" not in a and a[-2:] == ["--config", "c.toml"]
    b = aether.build_args("a.exe", 1900, "h2")
    assert "--h2" in b and "--fragment" in b
    for bad in (dict(protocol="x"), dict(mode="h9")):
        with pytest.raises(ValueError):
            aether.build_args("a.exe", 1, **bad)


def socks_server(answer=b"\x05\x00"):
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)

    def run():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            c.recv(3); c.sendall(answer); c.close()
    threading.Thread(target=run, daemon=True).start()
    return srv


def test_socks_ready_detects_real_socks_only():
    s = socks_server()
    assert aether.socks_ready(s.getsockname()[1]) is True
    s.close()
    bad = socks_server(b"HT")
    assert aether.socks_ready(bad.getsockname()[1]) is False
    bad.close()
    assert aether.socks_ready(1) is False


def test_manager_start_missing_exe_and_h3_to_h2_fallback(tmp_path, monkeypatch):
    m = aether.AetherManager(executable=tmp_path / "none.exe", data_dir=tmp_path / "d")
    with pytest.raises(aether.AetherError, match="not installed"):
        m.start()
    (tmp_path / "a.exe").write_bytes(b"x")
    m = aether.AetherManager(executable=tmp_path / "a.exe", data_dir=tmp_path / "d")
    launched = []

    class P:
        stdout = None
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): pass

    monkeypatch.setattr(m, "_launch", lambda port, mode, **kw: (launched.append((mode, kw)[0]), setattr(m, "process", P())))
    monkeypatch.setattr(aether, "free_port", lambda *a, **k: 1900)
    ready = lambda port: launched[-1] == "h2"                      # HTTP/2 is tried first and comes up
    t = [0.0]
    monkeypatch.setattr(aether.time, "time", lambda: t[0])
    port = m.start(wait=2, ready=ready, sleep=lambda s: t.__setitem__(0, t[0] + 1))
    assert port == 1900 and launched == ["h2"] and m.port == 1900


def test_manager_error_carries_log_tail(tmp_path, monkeypatch):
    (tmp_path / "a.exe").write_bytes(b"x")
    m = aether.AetherManager(executable=tmp_path / "a.exe", data_dir=tmp_path / "d")

    class Dead:
        stdout = None
        def poll(self): return 1
        def terminate(self): pass
    monkeypatch.setattr(m, "_launch", lambda port, mode, **kw: (m._lines.append("boom: no gateway"), setattr(m, "process", Dead())))
    monkeypatch.setattr(aether, "free_port", lambda *a, **k: 1900)
    with pytest.raises(aether.AetherError, match="boom: no gateway"):
        m.start(wait=1, ready=lambda p: False, sleep=lambda s: None)


# ---------------------------------------------------------------- integration with the rest
def test_socks_profile_becomes_xray_socks_outbound():
    cfg = generate_config([aether.warp_profile(1900)])
    o = cfg["outbounds"][0]
    assert o["protocol"] == "socks" and o["settings"]["servers"] == [{"address": "127.0.0.1", "port": 1900}]


def test_auto_search_ignores_the_local_warp_profile():
    seen = []

    def tester(exe, p, port, timeout=6):
        seen.append(p.get("name")); return -1

    class NoScan:
        def looks_cloudflare(self, p): return False
    autobypass.auto_run("x", [aether.warp_profile(1900)], lambda *a: None, tester=tester, doh_check=lambda: [], scanner=NoScan(),
                        relaxed_tester=None)
    assert seen == []


# ---------------------------------------------------------------- Tor modes
def test_build_args_tor_modes():
    t = aether.build_args("a.exe", 1900, "h3", tor="tor", tor_port=1905, tor_dir="td")
    assert "--tor" in t and t[t.index("--tor-bind") + 1] == "127.0.0.1:1905" and "--masque" in t and "--tor-dir" in t
    o = aether.build_args("a.exe", 1900, tor="tor-only")
    assert o[:4] == ["a.exe", "--bind", "127.0.0.1:1900", "--tor-only"] and "--masque" not in o
    with pytest.raises(ValueError):
        aether.build_args("a.exe", 1, tor="reverse")


def test_extract_pt_writes_only_the_pt_folder(tmp_path):
    import zipfile as zf, io as _io
    b = _io.BytesIO()
    with zf.ZipFile(b, "w") as z:
        z.writestr("aether-win/aether.exe", b"MZ"); z.writestr("aether-win/pt/obfs4.exe", b"O"); z.writestr("aether-win/pt/sub/snow.exe", b"S")
        z.writestr("aether-win/pt/../../evil.exe", b"E"); z.writestr("aether-win/README", b"r")
    assert aether.extract_pt(b.getvalue(), tmp_path) == 2
    assert (tmp_path / "pt" / "obfs4.exe").read_bytes() == b"O" and (tmp_path / "pt" / "sub" / "snow.exe").exists()
    assert not (tmp_path.parent / "evil.exe").exists() and not (tmp_path / "aether.exe").exists()


def test_tor_profile_and_kind_matching():
    p = aether.tor_profile(1901, "tor-only")
    assert aether.is_aether(p) and aether.needs_kind(p) == "tor-only" and p["group"] == "Tor" and p["port"] == 1901
    assert aether.needs_kind(aether.warp_profile(1900)) == "warp" and aether.needs_kind({"type": "vless"}) is None


def test_manager_tor_waits_on_the_tor_port_and_reports_missing_tor_support(tmp_path, monkeypatch):
    (tmp_path / "a.exe").write_bytes(b"x")
    m = aether.AetherManager(executable=tmp_path / "a.exe", data_dir=tmp_path / "d")
    seen = []

    class P:
        stdout = None
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): pass
    monkeypatch.setattr(m, "_launch", lambda port, mode, **kw: (seen.append((port, kw)), setattr(m, "process", P())))
    ports = iter([1900, 1901])
    monkeypatch.setattr(aether, "free_port", lambda *a, **k: next(ports))
    assert m.start(ready=lambda p: p == 1901, sleep=lambda s: None, kind="tor") == 1901       # Tor-in-tunnel: the SECOND port is the Tor one
    assert m.kind == "tor" and seen[0][1]["tor"] == "tor" and seen[0][1]["tor_port"] == 1901
    m.stop(); assert m.kind is None

    class Dead:
        stdout = None
        def poll(self): return 2
        def terminate(self): pass
    monkeypatch.setattr(m, "_launch", lambda port, mode, **kw: (m._lines.append("error: unexpected argument '--tor-only'"), setattr(m, "process", Dead())))
    monkeypatch.setattr(aether, "free_port", lambda *a, **k: 1900)
    with pytest.raises(aether.AetherError, match="no Tor support"):
        m.start(ready=lambda p: False, sleep=lambda s: None, kind="tor-only")
    with pytest.raises(ValueError):
        m.start(kind="nope")


def test_build_args_family_and_transport():
    assert "-4" in aether.build_args("a.exe", 1900) and "-6" not in aether.build_args("a.exe", 1900)
    v6 = aether.build_args("a.exe", 1900, "h3", family="6")
    assert "-6" in v6 and "-4" not in v6
    assert "--dual" in aether.build_args("a.exe", 1900, family="dual")
    w = aether.build_args("a.exe", 1900, "h3", protocol="wg", family="6")
    assert "--wg" in w and "-6" in w and "--h2" not in w
    assert "--gool" in aether.build_args("a.exe", 1900, protocol="gool")
    with pytest.raises(ValueError):
        aether.build_args("a.exe", 1, family="5")


def test_manager_wireguard_tries_one_mode_and_passes_choices(tmp_path, monkeypatch):
    (tmp_path / "a.exe").write_bytes(b"x")
    m = aether.AetherManager(executable=tmp_path / "a.exe", data_dir=tmp_path / "d")
    seen = []

    class Dead:
        stdout = None
        def poll(self): return 1
        def terminate(self): pass
    monkeypatch.setattr(m, "_launch", lambda port, mode, **kw: (seen.append((mode, kw)), setattr(m, "process", Dead())))
    monkeypatch.setattr(aether, "free_port", lambda *a, **k: 1900)
    with pytest.raises(aether.AetherError):
        m.start(ready=lambda p: False, sleep=lambda s: None, protocol="wg", family="6")
    assert len(seen) == 1 and seen[0][1]["protocol"] == "wg" and seen[0][1]["family"] == "6"        # no HTTP/2 retry for WireGuard


# ---------------------------------------------------------------- Psiphon modes
def test_build_args_psiphon_modes_and_region():
    p = aether.build_args("a.exe", 1900, "h3", psiphon="psiphon", psiphon_port=1905, psiphon_dir="pd", region="de")
    assert "--psiphon" in p and p[p.index("--psiphon-bind") + 1] == "127.0.0.1:1905" and "--masque" in p
    assert p[p.index("--psiphon-region") + 1] == "DE" and "--psiphon-dir" in p
    o = aether.build_args("a.exe", 1900, psiphon="psiphon-only")
    assert o[:4] == ["a.exe", "--bind", "127.0.0.1:1900", "--psiphon-only"] and "--masque" not in o
    for bad in (dict(psiphon="x"), dict(psiphon="psiphon", region="DEU"), dict(psiphon="psiphon", region="1;"), dict(tor="tor", psiphon="psiphon")):
        with pytest.raises(ValueError):
            aether.build_args("a.exe", 1, **bad)


def test_psiphon_profile_kind_matching():
    p = aether.psiphon_profile(1901, "psiphon-only")
    assert aether.is_aether(p) and aether.needs_kind(p) == "psiphon-only" and p["group"] == "Psiphon" and p["name"] == "Psiphon alone (Aether)"
    assert aether.psiphon_profile(1, "psiphon")["name"] == "Psiphon (Aether)"


def test_manager_psiphon_waits_on_second_port_and_reports_missing_binary(tmp_path, monkeypatch):
    (tmp_path / "a.exe").write_bytes(b"x")
    m = aether.AetherManager(executable=tmp_path / "a.exe", data_dir=tmp_path / "d")
    seen = []

    class P:
        stdout = None
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): pass
    monkeypatch.setattr(m, "_launch", lambda port, mode, **kw: (seen.append(kw), setattr(m, "process", P())))
    ports = iter([1900, 1901])
    monkeypatch.setattr(aether, "free_port", lambda *a, **k: next(ports))
    assert m.start(ready=lambda p: p == 1901, sleep=lambda s: None, kind="psiphon", region="NL") == 1901
    assert m.kind == "psiphon" and seen[0]["psiphon"] == "psiphon" and seen[0]["psiphon_port"] == 1901 and seen[0]["region"] == "NL" and seen[0]["tor"] is None
    m.stop()

    class Dead:
        stdout = None
        def poll(self): return 1
        def terminate(self): pass
    monkeypatch.setattr(m, "_launch", lambda port, mode, **kw: (m._lines.append("error: psiphon-tunnel-core not found"), setattr(m, "process", Dead())))
    monkeypatch.setattr(aether, "free_port", lambda *a, **k: 1900)
    with pytest.raises(aether.AetherError, match="pt/psiphon-tunnel-core"):
        m.start(ready=lambda p: False, sleep=lambda s: None, kind="psiphon-only")


def test_psiphon_tool_ends_up_next_to_the_exe(tmp_path):
    import zipfile as zf, io as _io
    b = _io.BytesIO()
    with zf.ZipFile(b, "w") as z:
        z.writestr("aether.exe", b"MZ"); z.writestr("pt/psiphon-tunnel-core.exe", b"PSI"); z.writestr("pt/obfs4proxy.exe", b"O")
    assert aether.extract_pt(b.getvalue(), tmp_path) == 2 and (tmp_path / "pt" / "psiphon-tunnel-core.exe").read_bytes() == b"PSI"


# ---------------------------------------------------------------- WhiteAesther-inspired additions
def test_wom_enroll_address_and_default_h2_first():
    a = aether.build_args("aether.exe", protocol="wom", mode="h2")
    assert "--wg-over-masque" in a and "--h2" in a and "--wom" not in a
    b = aether.build_args("aether.exe", enroll_address="188.114.97.6")
    assert b[b.index("--enroll-address") + 1] == "188.114.97.6"
    with pytest.raises(ValueError):
        aether.build_args("aether.exe", enroll_address="a b;rm")
    import inspect
    assert inspect.signature(aether.AetherManager.start).parameters["modes"].default == ("h2", "h3")


def test_supported_flags_reads_help_text_and_survives_errors():
    class R:  # noqa
        stdout = "Usage: aether [OPTIONS]\n  --ech <v>   x\n  --enroll-address <a>\n  -4\n"; stderr = ""
    assert aether.supported_flags("x", run=lambda *a, **k: R()) == {"--ech", "--enroll-address"}
    def boom(*a, **k): raise OSError("no")
    assert aether.supported_flags("x", run=boom) == set()


def test_identity_backup_restore_roundtrip_and_refusals(tmp_path):
    d = tmp_path / "d"; d.mkdir()
    assert not aether.identity_exists(d)
    with pytest.raises(aether.AetherError):
        aether.backup_identity(tmp_path / "b.toml", d)
    (d / "aether.toml").write_text('private_key = "abc"\nid = "1234567890123456"\n', encoding="utf-8")
    aether.backup_identity(tmp_path / "b.toml", d)
    (d / "aether.toml").write_text('private_key = "NEW"\nid = "99999999999999999"\n', encoding="utf-8")
    aether.restore_identity(tmp_path / "b.toml", d)
    assert 'abc' in (d / "aether.toml").read_text() and (d / "aether.toml.bak").exists()
    (tmp_path / "big.toml").write_bytes(b"a=" + b"x" * 70000)
    with pytest.raises(aether.AetherError):
        aether.restore_identity(tmp_path / "big.toml", d)
    (tmp_path / "bin.toml").write_bytes(b"\x00\x01\x02=")
    with pytest.raises(aether.AetherError):
        aether.restore_identity(tmp_path / "bin.toml", d)


def test_upstream_without_identity_warns_and_wom_needs_the_flag(tmp_path, monkeypatch):
    (tmp_path / "a.exe").write_bytes(b"x")
    m = aether.AetherManager(executable=tmp_path / "a.exe", data_dir=tmp_path / "d")
    monkeypatch.setattr(aether, "supported_flags", lambda exe, run=None: set())
    with pytest.raises(aether.AetherError, match="wg-over-masque"):
        m.start(protocol="wom")
    m.upstream = "socks5://127.0.0.1:1900"
    seen = []
    monkeypatch.setattr(m, "_launch", lambda *a, **k: (_ for _ in ()).throw(aether.AetherError("stop here")))
    with pytest.raises(aether.AetherError, match="stop here"):
        m.start(progress=seen.append)
    assert any("no saved identity" in s for s in seen)
