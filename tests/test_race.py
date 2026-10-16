import threading

from app.core import autobypass as ab
from tests.test_autobypass import tls


def test_race_picks_fastest_ip_for_first_working_method():
    ports, lock = [], threading.Lock()
    speed = {"1.1.1.1": 90, "2.2.2.2": 30, "3.3.3.3": -1}

    def tester(exe, p, port, timeout=6):
        with lock:
            ports.append(port)
        return speed[p["address_override"]] if p["bypass"] == "pattng" else -1
    groups = [[{"bypass": m, "address_override": ip} for ip in speed] for m in ("off", "pattng", "standard")]
    v, ms = ab.find_variant_race("x", tls("a"), ab.BASE_PORT, groups, tester=tester)
    assert v == {"bypass": "pattng", "address_override": "2.2.2.2"} and ms == 30
    assert len(set(ports[:3])) == 3                                   # parallel tests never share a port


def test_race_none_when_nothing_works_and_cancel():
    groups = [[{"bypass": "off", "address_override": "1.1.1.1"}]]
    assert ab.find_variant_race("x", tls("a"), ab.BASE_PORT, groups, tester=lambda *a, **k: -1) is None
    assert ab.find_variant_race("x", tls("a"), ab.BASE_PORT, groups, cancelled=lambda: True,
                                tester=lambda *a, **k: 5) is None


def test_ports_of_different_profiles_do_not_overlap():
    seen = {}

    def tester(exe, p, port, timeout=6):
        seen.setdefault(p["name"], set()).add(port); return -1
    g = [[{"bypass": "off", "address_override": ip} for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3")]]
    for n, name in enumerate("abc"):
        ab.find_variant_race("x", tls(name), ab.BASE_PORT + n, g, tester=tester)
    allp = [x for s in seen.values() for x in s]
    assert len(allp) == len(set(allp)) == 9


def test_auto_phase2_races_best_ips_and_keeps_winner_ip():
    class Scan:
        def looks_cloudflare(self, p): return True
        def scan_target(self, p): return 443, "a.workers.dev"
        def load_ranges(self): return ["1.0.0.0/24"]
        def sample_ips(self, r, n): return ["9.9.9.9"]
        def scan(self, ips, port, sni, cb, cancelled=lambda: False):
            cb("104.20.1.1", 80, "FRA"); cb("104.20.2.2", 40, "AMS"); cb("104.20.3.3", 60, "CDG")
    wins, status = [], []

    def tester(exe, p, port, timeout=6):
        return {"104.20.1.1": 80, "104.20.2.2": 40, "104.20.3.3": 60}.get(p.get("address_override"), -1)
    ab.auto_run("x", [tls("a")], lambda p, v, ms: wins.append((v, ms)), on_status=status.append, tester=tester,
                doh_check=lambda: [], want=1, workers=3, scanner=Scan(), relaxed_tester=None)
    assert wins and wins[0][0]["address_override"] == "104.20.2.2"      # AMS, the fastest of the three
    assert any("racing the best 3" in s for s in status)
