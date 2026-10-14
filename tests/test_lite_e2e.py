"""Real Xray, real sockets: servers are local Shadowsocks servers (Xray itself)."""
import base64, http.server, json, os, shutil, subprocess, threading, time
from pathlib import Path
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
XRAY = shutil.which("xray") or "/tmp/xr/xray"
pytestmark = pytest.mark.skipif(not Path(XRAY).exists(), reason="no xray binary")


def ss_link(port, name, host="127.0.0.2"):
    cred = base64.urlsafe_b64encode(b"chacha20-ietf-poly1305:pw").decode().rstrip("=")
    return f"ss://{cred}@{host}:{port}#{name}"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(204); self.end_headers()
        def log_message(self, *a): pass
    web = http.server.HTTPServer(("127.0.0.1", 18090), H)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    procs = []
    for port in (25001, 25002):
        cfg = tmp_path / f"srv{port}.json"
        cfg.write_text(json.dumps({"inbounds": [{"listen": "127.0.0.2", "port": port, "protocol": "shadowsocks",
            "settings": {"method": "chacha20-ietf-poly1305", "password": "pw", "network": "tcp,udp"}}],
            "outbounds": [{"protocol": "freedom", "settings": {"finalRules": [{"action": "allow"}]}}]}))   # Xray 26.7 blocks loopback targets by default
        procs.append(subprocess.Popen([XRAY, "run", "-c", str(cfg)], cwd=str(Path(XRAY).parent),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(1.5)
    import app.lite.paths as P
    import app.core.delay_all as D
    monkeypatch.setattr(P, "xray_exe", lambda: Path(XRAY))
    import app.lite.engine as E
    monkeypatch.setattr(E, "PROBE_URL", "http://127.0.0.1:18090/")       # no internet needed
    monkeypatch.setattr(D, "TEST_URL", "http://127.0.0.1:1/")            # bogus: proves Lite passes its own probe URL
    yield tmp_path
    for p in procs: p.terminate()
    web.shutdown()


@pytest.fixture(autouse=True)
def no_modal(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    for n in ('warning', 'critical', 'information'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: print('MODAL:', a[1:3])))


def pump(app, cond, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond(): return True
        time.sleep(0.05)
    return False


def through_tunnel(win, tries=6):
    """Like a browser: retry a few times (Xray's WebSocket transport drops some tiny requests on loopback)."""
    from app.utils.latency import real_delay
    for i in range(tries):
        try:
            return real_delay(f"http://127.0.0.1:{win.http}", "http://127.0.0.1:18090/", timeout=6)
        except Exception:
            if i == tries - 1: raise
            time.sleep(0.3)


def make_window(monkeypatch, wmod):
    monkeypatch.setattr(wmod, "exit_info", lambda proxy, t=10: {"query": "1.2.3.4", "country": "Testland"})
    w = wmod.LiteWindow()
    monkeypatch.setattr(w, "xray_settings", lambda: {"routing": {"lan": False, "iran": True}})   # so 127.x really goes through the tunnel
    return w


def test_paste_connect_auto_picks_working_servers_and_failover_config(world, monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import app.lite.window as wmod
    w = make_window(monkeypatch, wmod)
    dead = ss_link(25999, "dead1") + "\n" + ss_link(25998, "dead2")
    w.handle_text(ss_link(25001, "live1") + "\n" + dead + "\n" + ss_link(25002, "live2"))
    assert len(w.profiles) == 4 and w.empty.isHidden()

    w.btn.click()                                                   # the one button the family presses
    assert pump(app, lambda: w.state == "connected" and w.btn.isEnabled() and w.xray.running)
    cfg = json.loads(Path("configs/active.json").read_text())
    assert cfg["routing"]["balancers"][0]["strategy"]["type"] == "leastPing"          # fail-over between the 2 live ones
    assert sorted(o["settings"]["servers"][0]["port"] for o in cfg["outbounds"] if o.get("protocol") == "shadowsocks") == [25001, 25002]
    assert pump(app, lambda: "Testland" in w.sub.text())            # shows where you exit
    assert through_tunnel(w) >= 0                                   # real traffic passes

    w.btn.click()                                                   # disconnect
    assert w.state == "idle" and not w.xray.running
    assert {p["name"] for p in w.profiles if (p.get("delay") or -1) >= 0} == {"live1", "live2"}
    assert next(p for p in w.profiles if p["name"] == "dead1")["delay"] == -1
    w.close()


def test_manual_pick_and_all_dead_message(world, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    import app.lite.window as wmod
    w = make_window(monkeypatch, wmod)
    w.handle_text(ss_link(25001, "live1") + "\n" + ss_link(25002, "live2"))
    w.combo.setCurrentIndex(w.combo.findText("live2", Qt_MatchContains()))      # choose one server
    w.btn.click()
    assert pump(app, lambda: w.state == "connected" and w.btn.isEnabled())
    cfg = json.loads(Path("configs/active.json").read_text())
    assert "balancers" not in cfg["routing"] and [o for o in cfg["outbounds"] if o["tag"] == "p0"][0]["settings"]["servers"][0]["port"] == 25002
    assert through_tunnel(w) >= 0
    w.btn.click(); assert w.state == "idle"

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[2])))
    w.profiles[:] = []; w.settings["selected"] = "auto"
    w.handle_text(ss_link(25997, "d1") + "\n" + ss_link(25996, "d2")); w.refresh_combo()
    w.btn.click()
    assert pump(app, lambda: shown) and w.state == "idle" and not w.xray.running
    w.close()


def test_cancel_while_finding_and_close_stops_xray(world, monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import app.lite.window as wmod
    w = make_window(monkeypatch, wmod)
    w.handle_text(ss_link(25001, "live1"))
    w.btn.click(); assert w.state == "finding"
    w.btn.click(); assert w.state == "idle"                          # cancel
    time.sleep(0.5); app.processEvents(); assert not w.xray.running
    w.btn.click()
    assert pump(app, lambda: w.state == "connected" and w.btn.isEnabled())
    pid = w.xray.process.pid
    w.close()
    assert not w.xray.running


def Qt_MatchContains():
    from PySide6.QtCore import Qt
    return Qt.MatchContains


UUID = "d65cc14c-f53f-4fe2-b262-97856601319c"


@pytest.fixture
def tls_server(world):
    """VLESS + WebSocket + real TLS (self-signed) on 127.0.0.2:8443 - the 'TLS door' of a server exported on a plain port."""
    subprocess.run([XRAY, "tls", "cert", "-domain=hy.test", "-file=srv"], cwd=str(world), capture_output=True)
    cfg = world / "tls_srv.json"
    cfg.write_text(json.dumps({"inbounds": [{"listen": "127.0.0.2", "port": 8443, "protocol": "vless",
        "settings": {"clients": [{"id": UUID}], "decryption": "none"},
        "streamSettings": {"network": "ws", "security": "tls", "wsSettings": {"path": "/ws"},
            "tlsSettings": {"certificates": [{"certificateFile": str(world / "srv.crt"), "keyFile": str(world / "srv.key")}]}}}],
        "outbounds": [{"protocol": "freedom", "settings": {"finalRules": [{"action": "allow"}]}}]}))
    p = subprocess.Popen([XRAY, "run", "-c", str(cfg)], cwd=str(Path(XRAY).parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    yield world
    p.terminate()


def test_plain_profile_is_upgraded_to_tls_automatically(tls_server, monkeypatch):
    """Exported as plain port 8080 (dead). Only the TLS port 8443 works -> Connect must find it by itself."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import app.lite.window as wmod
    w = make_window(monkeypatch, wmod)
    w.handle_text(f"vless://{UUID}@127.0.0.2:8080?type=ws&path=%2Fws&security=none&host=hy.test#plainCF")
    assert len(w.profiles) == 1 and w.profiles[0]["security"] in ("", "none")
    w.btn.click()
    assert pump(app, lambda: (w.state == "connected" and w.btn.isEnabled() and w.xray.running) or w.state == "idle" and w.profiles[0].get("tls_tried"), 60)
    assert w.state == "connected"
    cfg = json.loads(Path("configs/active.json").read_text())
    out = [o for o in cfg["outbounds"] if o["tag"] == "p0"][0]
    assert out["settings"]["vnext"][0]["port"] == 8443 and out["streamSettings"]["security"] == "tls"
    assert len(out["streamSettings"]["tlsSettings"]["pinnedPeerCertSha256"]) == 64     # self-signed cert pinned, not 'insecure'
    assert through_tunnel(w) >= 0
    assert [p["name"] for p in w.profiles] == ["plainCF", "plainCF [TLS 8443]"]         # original kept, TLS version added
    w.btn.click(); w.close()


def test_menu_convert_and_honest_failure_when_no_tls_exists(world, monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import app.lite.window as wmod
    shown = []
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[2])))
    w = make_window(monkeypatch, wmod)
    w.handle_text(f"vless://{UUID}@127.0.0.2:8080?type=ws&path=%2Fws&security=none#nope")   # nothing listens anywhere
    w.btn.click()
    assert pump(app, lambda: shown, 60)
    assert w.state == "idle" and "TLS" in shown[0] and "اضافه" in shown[0]                   # clear, truthful message
    assert len(w.profiles) == 1                                                              # nothing was faked
    w.close()
