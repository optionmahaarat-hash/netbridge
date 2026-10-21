from app.core import autobypass as ab

def tls(n, port=443): return {"name": n, "type": "vless", "server": "1.1.1.1", "port": port, "uuid": "u", "security": "tls", "sni": "a.workers.dev"}
def plain(n): return {"name": n, "type": "vless", "server": "2.2.2.2", "port": 80, "uuid": "u", "security": ""}

def run(profiles, works, doh=("https://dns.google/dns-query",), want=2, scanner=None):
    wins, calls = [], []
    def tester(exe, p, port, timeout=6):
        calls.append((p["name"], p.get("bypass"), p.get("address_override")))
        return works(p)
    r = ab.auto_run("x", profiles, lambda p, v, ms: wins.append((p["name"], v, ms)), tester=tester,
                    doh_check=lambda: list(doh), want=want, workers=1, scanner=scanner or _NoScan())
    return r, wins, calls

class _NoScan:
    def looks_cloudflare(self, p): return False

def test_picks_first_method_that_works_and_skips_ech_without_doh():
    r, wins, calls = run([tls("a")], lambda p: 120 if p.get("bypass") == "pattng" else -1, doh=())
    assert wins[0][1] == {"bypass": "pattng"} and r["tls"] == 1
    assert [c[1] for c in calls] == ["off", "pattng"]
    assert all(c[1] != "ech" for c in calls)

def test_ech_only_with_reachable_doh():
    r, wins, calls = run([tls("a")], lambda p: 90 if p.get("bypass") == "ech" else -1)
    assert wins[0][1]["ech"] == "cloudflare-ech.com+https://dns.google/dns-query"

def test_extra_ech_forms_are_tried_even_without_doh():
    r, wins, calls = run([tls("a")], lambda p: 80 if p.get("ech") == "h2c://1.1.1.1/dns-query" else -1, doh=())
    assert wins[0][1]["ech"] == "h2c://1.1.1.1/dns-query"
    assert "crypto.cloudflare.com+udp://1.1.1.1" in ab.ECH_EXTRA

def test_stops_after_want_winners():
    ps = [tls(str(i)) for i in range(10)]
    r, wins, _ = run(ps, lambda p: 50, want=3)
    assert len(wins) == 3

def test_plain_is_last_resort_and_flagged():
    r, wins, _ = run([tls("a"), plain("p")], lambda p: 70 if not ab.is_tls(p) else -1)
    assert r["tls"] == 0 and r["plain"] == 1 and r["insecure_fallback"] is True

def test_plain_not_tried_when_tls_works():
    r, wins, calls = run([tls("a"), plain("p")], lambda p: 70 if ab.is_tls(p) else -1, want=1)
    assert r["insecure_fallback"] is False and all(c[0] != "p" for c in calls)

def test_clean_ip_phase():
    class Scan:
        def looks_cloudflare(self, p): return True
        def scan_target(self, p): return 443, "a.workers.dev"
        def load_ranges(self): return ["1.0.0.0/24"]
        def sample_ips(self, r, n): return ["9.9.9.9"]
        def scan(self, ips, port, sni, cb, cancelled=lambda: False): cb("104.20.1.1", 80, "FRA")
    r, wins, calls = run([tls("a")], lambda p: 60 if p.get("address_override") == "104.20.1.1" else -1, scanner=Scan())
    assert r["tls"] == 1 and wins[0][1]["address_override"] == "104.20.1.1"

def test_apply_variant_keeps_other_fields():
    p = dict(tls("a"), chain_key="k", ech="old", fm="{}")
    ab.apply_variant(p, {"bypass": "pattng"})
    assert p["bypass"] == "pattng" and "ech" not in p and p["chain_key"] == "k" and p["fm"] == "{}"

def test_dns_query_shape():
    q = ab._dns_query("cloudflare-ech.com")
    assert q[:2] == b"\x12\x34" and q.endswith(b"\x00\x41\x00\x01")


# ---- strict site verification (the basic generate_204 test is not enough for YouTube/Instagram)
from app.utils import latency


def _fake_fetch(table):
    def fetch(proxy, url, timeout, read=20000):
        v = table[url]
        if isinstance(v, Exception):
            raise v
        return v
    return fetch


def test_check_sites_all_ok():
    f = _fake_fetch({"https://www.youtube.com/generate_204": (204, 300),
                     "https://www.instagram.com/": (200, 500),
                     "https://www.google.com/generate_204": (204, 200)})
    res = latency.check_sites("http://x", fetch=f)
    assert latency.sites_ok(res) and latency.sites_ms(res) == 333


def test_check_sites_one_blocked_fails_the_profile():
    f = _fake_fetch({"https://www.youtube.com/generate_204": (204, 300),
                     "https://www.instagram.com/": TimeoutError("timed out"),
                     "https://www.google.com/generate_204": (204, 200)})
    res = latency.check_sites("http://x", fetch=f)
    assert not latency.sites_ok(res)
    assert [r[0] for r in res if not r[1]] == ["Instagram"]


def test_check_sites_wrong_status_is_failure():
    f = _fake_fetch({"https://www.youtube.com/generate_204": (403, 300),
                     "https://www.instagram.com/": (200, 500),
                     "https://www.google.com/generate_204": (204, 200)})
    assert not latency.sites_ok(latency.check_sites("http://x", fetch=f))


def test_relaxed_fallback_when_nothing_passes_strict():
    calls = []
    def strict(exe, p, port, timeout=6): calls.append("strict"); return -1
    def relaxed(exe, p, port, timeout=6): calls.append("relaxed"); return 80
    wins = []
    r = ab.auto_run("x", [tls("a")], lambda p, v, ms: wins.append(ms), tester=strict, relaxed_tester=relaxed,
                    doh_check=lambda: [], want=1, workers=1, scanner=_NoScan())
    assert r["relaxed_fallback"] is True and wins == [80] and "relaxed" in calls


def test_no_relaxed_fallback_when_strict_passes():
    def strict(exe, p, port, timeout=6): return 90
    def relaxed(exe, p, port, timeout=6): raise AssertionError("must not run")
    r = ab.auto_run("x", [tls("a")], lambda *a: None, tester=strict, relaxed_tester=relaxed,
                    doh_check=lambda: [], want=1, workers=1, scanner=_NoScan())
    assert r["relaxed_fallback"] is False


def test_firewall_order():
    base = ab.variants(tls("a"), ["https://dns.google/dns-query"], ipv6=True)
    kinds = lambda L: [v["bypass"] for v in L]
    for fw in ("auto", "mci", "irancell"):
        o = ab.variants(tls("a"), ["https://dns.google/dns-query"], ipv6=True, firewall=fw)
        k = kinds(o)
        assert k[-3:] == ["ech", "ech", "ech"] or k[-4:].count("ech") >= 3      # ECH last (cloudflare-ech.com is blocked now)
        assert sorted(map(str, o)) == sorted(map(str, base))                    # same methods, only reordered
    ir = ab.variants(tls("a"), ["https://dns.google/dns-query"], firewall="irancell")
    assert ir[0]["bypass"] not in ("off", "ech")                                # fragment first on Irancell


