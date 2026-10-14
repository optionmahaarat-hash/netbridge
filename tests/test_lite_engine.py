import json, threading, http.server, socketserver, base64
from app.lite import engine as E

UUID = "d65cc14c-f53f-4fe2-b262-97856601319c"
VL = f"vless://{UUID}@1.2.3.4:443?security=tls&sni=a.workers.dev&type=ws&path=%2Fx#one"
VL2 = f"vless://{UUID}@5.6.7.8:443?security=tls&sni=a.workers.dev&type=ws&path=%2Fx#two"
SS = "ss://" + base64.urlsafe_b64encode(b"chacha20-ietf-poly1305:pw").decode().rstrip("=") + "@9.9.9.9:8388#ss"


def test_classify_clipboard():
    assert E.classify_text(VL) == "links" and E.classify_text("hello\n" + SS) == "links"
    assert E.classify_text('{"outbounds": []}') == "json"
    assert E.classify_text("https://example.com/sub/abc") == "subscription"
    assert E.classify_text("just some words") is None and E.classify_text("") is None and E.classify_text(None) is None


def test_add_text_dedupes_and_counts():
    ps = []
    added, dup, bad, errs = E.add_text(ps, VL + "\n" + VL + "\n" + SS + "\nvless://broken")
    assert (added, dup) == (2, 1) and len(ps) == 2 and len(errs) == 1
    assert E.add_text(ps, VL)[:2] == (0, 1)


def sub_server(body_fn):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            b = body_fn().encode(); self.send_response(200); self.end_headers(); self.wfile.write(b)
        def log_message(self, *a): pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/sub"


def test_subscription_add_and_refresh_replaces_group():
    state = {"body": base64.b64encode((VL + "\n" + VL2).encode()).decode()}
    srv, url = sub_server(lambda: state["body"])
    try:
        ps, st = [], E.load_settings() if False else json.loads(json.dumps(E.DEFAULTS))
        r = E.add_subscription(ps, url, st)
        assert r[0] == 2 and st["subs"][0]["url"] == url and ps[0]["group"] == "127.0.0.1"
        ps[0]["delay"] = 120                                               # remembered across refresh
        manual = E.add_text(ps, SS)                                       # not part of the subscription
        state["body"] = base64.b64encode(VL.encode()).decode()            # server dropped VL2
        total, failed = E.refresh_subscriptions(ps, st)
        assert total == 1 and not failed
        assert sorted(p["name"] for p in ps) == ["one", "ss"]            # VL2 gone, manual one kept
        assert next(p for p in ps if p["name"] == "one")["delay"] == 120
    finally:
        srv.shutdown()


def test_rank_and_choose_connection():
    a, b, c, d = {"delay": 300}, {"delay": 80}, {}, {"delay": -1}
    assert E._rank(b) < E._rank(a) < E._rank(c) < E._rank(d)
    assert E.choose_connection([({"n": 1}, 10), ({"n": 2}, 20)])[1] == "auto"
    assert E.choose_connection([({"n": 1}, 10)]) == ([{"n": 1}], "manual")


def test_pin_pending_marks_failures():
    ps = [{"insecure": True}, {"insecure": True, "pcs": "x"}, {"type": "vless"}]
    def fetch(p):
        raise RuntimeError("down")
    assert E.pin_pending(ps, fetch) == 0 and ps[0]["pin_failed"] and "pin_failed" not in ps[1]
    ps[0].pop("pin_failed")
    assert E.pin_pending(ps, lambda p: "abc") == 1 and ps[0]["pcs"] == "abc"


def test_clear_stale_proxy_only_when_dead(monkeypatch):
    from app.core import system_proxy as sp
    calls = []
    monkeypatch.setattr(sp, "current", lambda: (True, "127.0.0.1:10809"))
    monkeypatch.setattr(sp, "set_proxy", lambda on, *a: calls.append(on))
    assert sp.clear_stale(lambda port: False) is True and calls == [False]        # nothing listens -> stale
    calls.clear()
    assert sp.clear_stale(lambda port: True) is False and not calls               # another VPN app owns it -> untouched
    monkeypatch.setattr(sp, "current", lambda: (True, "proxy.corp:8080"))
    assert sp.clear_stale(lambda port: False) is False                            # not ours -> untouched
    monkeypatch.setattr(sp, "current", lambda: (False, "127.0.0.1:10809"))
    assert sp.clear_stale(lambda port: False) is False


def test_seed_profiles_first_run_only(tmp_path):
    import json
    from app.lite import engine as E
    seed = tmp_path / "seed.json"; data = tmp_path / "data" / "profiles.json"
    good = {"name": "a", "type": "vless", "server": "1.2.3.4", "port": 443, "uuid": "u"}
    seed.write_text(json.dumps([good, {"name": "broken"}]))
    assert E.seed_profiles(data, seed) == 1                      # valid ones only
    assert json.loads(data.read_text()) == [good]
    data.write_text("[]")                                        # user deleted everything: must stay empty
    assert E.seed_profiles(data, seed) == 0 and json.loads(data.read_text()) == []
    assert E.seed_profiles(tmp_path / "x" / "p.json", tmp_path / "missing.json") == 0


def test_auto_find_applies_winning_method_and_prefers_tls():
    from app.lite import engine as E
    ps = [{"name": "a", "security": "tls"}, {"name": "b", "security": "tls"}, {"name": "c", "security": ""}]

    def runner(exe, profiles, on_win, cancelled, want, **kw):
        on_win(profiles[1], {"bypass": "ech", "ech": "x+y"}, 300)
        on_win(profiles[0], {"bypass": "off"}, 100)
        on_win(profiles[2], {"bypass": "off"}, 50)
        return {"tls": 2}
    ok, res = E.auto_find("x", ps, runner=runner)
    assert [(p["name"], ms) for p, ms in ok] == [("a", 100), ("b", 300)]      # plain one dropped while TLS works
    assert ps[1]["bypass"] == "ech" and ps[1]["delay"] == 300
