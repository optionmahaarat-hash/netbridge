from app.core import aether


def test_parse_bridges_cleans_and_flags():
    good, bad = aether.parse_bridges("""# my bridges
Bridge obfs4 192.0.2.55:38114 316E643333645F6D79216558614D3931657A5F5F cert=AB iat-mode=0
obfs4 192.0.2.55:38114 316E643333645F6D79216558614D3931657A5F5F cert=AB iat-mode=0
webtunnel [2001:db8::1]:443 ABCDEF url=https://x.example/p
192.0.2.9:9001 316E643333645F6D79216558614D3931657A5F5F
hello world
obfs4
""")
    assert len(good) == 3 and good[0].startswith("obfs4 ") and good[2].startswith("192.0.2.9")
    assert bad == ["hello world", "obfs4"]


def test_build_args_bridges_only_for_tor():
    a = aether.build_args("a.exe", 1900, tor="tor-only", bridge_file="b.txt", bridges_now=True)
    assert a[a.index("--tor-bridge-file") + 1] == "b.txt" and "--tor-bridges" in a
    w = aether.build_args("a.exe", 1900, bridge_file="b.txt", bridges_now=True)
    assert "--tor-bridge-file" not in w and "--tor-bridges" not in w


def test_manager_writes_bridge_file(tmp_path, monkeypatch):
    m = aether.AetherManager(executable=tmp_path / "a.exe", data_dir=tmp_path)
    m.bridges, m.bridges_now = ["obfs4 192.0.2.55:1 AA cert=x"], True
    seen = {}
    class P:
        stdout = iter(()); 
        def poll(self): return None
    monkeypatch.setattr(aether.subprocess, "Popen", lambda args, **kw: (seen.setdefault("args", args), P())[1])
    m._launch(1900, "h3", tor="tor-only")
    assert (tmp_path / "tor_bridges.txt").read_text().strip() == "obfs4 192.0.2.55:1 AA cert=x"
    assert "--tor-bridges" in seen["args"]


def test_stop_during_start_is_cancel_not_crash(tmp_path, monkeypatch):
    import pytest
    m = aether.AetherManager(executable=tmp_path / "a.exe", data_dir=tmp_path)
    (tmp_path / "a.exe").write_bytes(b"x")
    class P:
        stdout = iter(())
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): pass
    monkeypatch.setattr(aether.subprocess, "Popen", lambda *a, **k: P())
    def ready(port):
        m.process = None                                   # the user pressed Disconnect meanwhile
        return False
    with pytest.raises(aether.AetherError, match="cancelled"):
        m.start(ready=ready, sleep=lambda s: None, kind="tor-only")


def test_psiphon_mode_and_noize_flags():
    a = aether.build_args("aether.exe", psiphon="psiphon-only", psiphon_mode="cdn")
    assert a[a.index("--psiphon-mode") + 1] == "cdn"
    b = aether.build_args("aether.exe", noize="gfw")
    assert b[b.index("--noize") + 1] == "gfw"
    assert "--psiphon-mode" not in aether.build_args("aether.exe", psiphon="psiphon-only")
    assert aether.build_args("aether.exe")[aether.build_args("aether.exe").index("--noize") + 1] == "firewall"
    for bad in ({"psiphon_mode": "x"}, {"noize": "x"}):
        try:
            aether.build_args("aether.exe", **bad); raise AssertionError("accepted")
        except ValueError:
            pass
