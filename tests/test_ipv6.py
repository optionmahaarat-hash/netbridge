"""IPv6: scanner ranges and sampling, the route check, and IPv6 entry points in AUTO."""
import ipaddress
import random

import pytest

from app.core import autobypass as ab
from app.core import ipscan
from app.core.config_generator import generate_xray_config


def tls(n, server="vpn.example.com", port=443):
    return {"name": n, "type": "vless", "server": server, "port": port, "uuid": "123e4567-e89b-12d3-a456-426614174000",
            "security": "tls", "sni": "a.workers.dev"}


@pytest.fixture(autouse=True)
def clean_cache():
    ab._V6.clear()
    yield
    ab._V6.clear()


# ------------------------------------------------------------------ scanner
def test_fallback_v6_ranges_are_valid_v6():
    nets = [ipaddress.ip_network(r) for r in ipscan.FALLBACK_RANGES6]
    assert nets and all(n.version == 6 for n in nets)


def test_v6_only_sampling_is_distinct_and_inside_the_ranges():
    ips = ipscan.sample_ips(ipscan.FALLBACK_RANGES6, 100, random.Random(2))
    assert len(ips) == len(set(ips)) == 100
    nets = [ipaddress.ip_network(r) for r in ipscan.FALLBACK_RANGES6]
    assert all(any(ipaddress.ip_address(i) in n for n in nets) for i in ips)


def test_mixed_sampling_does_not_let_ipv6_crowd_out_ipv4():
    ips = ipscan.sample_ips(ipscan.FALLBACK_RANGES + ipscan.FALLBACK_RANGES6, 200, random.Random(3))
    v6 = [i for i in ips if ipscan.is_ipv6(i)]
    assert len(ips) == 200 and len(v6) == 100                         # 50 / 50 by default, not 100 % IPv6 by size
    assert len(ipscan.sample_ips(ipscan.FALLBACK_RANGES + ipscan.FALLBACK_RANGES6, 200, random.Random(3), v6_share=0.25)
               ) == 200
    assert not any(ipscan.is_ipv6(i) for i in ipscan.sample_ips(ipscan.FALLBACK_RANGES, 50, random.Random(4)))


def test_load_ranges6_falls_back_when_offline_or_wrong_family(monkeypatch):
    def boom(*a, **k): raise OSError("offline")
    monkeypatch.setattr(ipscan.urllib.request, "urlopen", boom)
    assert ipscan.load_ranges6() == ipscan.FALLBACK_RANGES6

    class R:
        def __init__(self, t): self.t = t
        def read(self): return self.t.encode()
    monkeypatch.setattr(ipscan.urllib.request, "urlopen", lambda *a, **k: R("1.0.0.0/24\n"))      # an IPv4 list is refused
    assert ipscan.load_ranges6() == ipscan.FALLBACK_RANGES6
    monkeypatch.setattr(ipscan.urllib.request, "urlopen", lambda *a, **k: R("2606:4700::/32\n2400:cb00::/32\n"))
    assert ipscan.load_ranges6() == ["2606:4700::/32", "2400:cb00::/32"]


def test_has_ipv6_follows_the_routing_table(monkeypatch):
    class S:
        def __init__(self, ok): self.ok = ok
        def connect(self, addr):
            if not self.ok: raise OSError("Network is unreachable")
        def close(self): pass
    monkeypatch.setattr(ipscan.socket, "socket", lambda *a: S(True))
    assert ipscan.has_ipv6() is True
    monkeypatch.setattr(ipscan.socket, "socket", lambda *a: S(False))
    assert ipscan.has_ipv6() is False


# ------------------------------------------------------------------ AUTO
def test_variants_without_ipv6_are_unchanged():
    v = ab.variants(tls("a"), doh_urls=())
    assert all("ip6" not in x for x in v)


def test_ipv6_variants_come_last_and_only_for_servers_given_by_name():
    v = ab.variants(tls("a"), doh_urls=["https://dns.google/dns-query"], ipv6=True)
    assert [x for x in v if x.get("ip6")] == [{"bypass": "off", "ip6": True}, {"bypass": "pattng", "ip6": True}]
    assert v[-1].get("ip6") and not v[0].get("ip6")
    assert all("ip6" not in x for x in ab.variants(tls("a", server="1.2.3.4"), ipv6=True))
    assert all("ip6" not in x for x in ab.variants(tls("a", server="2606:4700::1"), ipv6=True))
    assert all("ip6" not in x for x in ab.variants(dict(tls("a"), address_override="104.20.1.1"), ipv6=True))
    assert all("ip6" not in x for x in ab.variants(tls("a"), clean_ip="104.20.1.1", ipv6=True))


def test_with_resolves_the_aaaa_record(monkeypatch):
    monkeypatch.setattr(ab.socket, "getaddrinfo", lambda *a, **k: [(10, 1, 6, "", ("2606:4700::6810:84e5", 443, 0, 0))])
    p = ab._with(tls("a"), {"bypass": "off", "ip6": True})
    assert p["address_override"] == "2606:4700::6810:84e5" and "ip6" not in p and p["bypass"] == "off"
    assert p["server"] == "vpn.example.com" and p["sni"] == "a.workers.dev"          # name / SNI stay


def test_server_without_aaaa_skips_the_ipv6_variants(monkeypatch):
    def none(*a, **k): raise OSError("no AAAA")
    monkeypatch.setattr(ab.socket, "getaddrinfo", none)
    calls = []
    def tester(exe, p, port, timeout=6):
        calls.append(p.get("address_override")); return -1
    r = ab.find_variant("x", tls("a"), 1, [{"bypass": "off", "ip6": True}, {"bypass": "pattng", "ip6": True}], tester=tester)
    assert r is None and calls == []                                                  # never even tested


def test_apply_variant_stores_the_ipv6_address(monkeypatch):
    monkeypatch.setattr(ab.socket, "getaddrinfo", lambda *a, **k: [(10, 1, 6, "", ("2606:4700::1", 443, 0, 0))])
    p = tls("a")
    ab.apply_variant(p, {"bypass": "pattng", "ip6": True})
    assert p["bypass"] == "pattng" and p["address_override"] == "2606:4700::1"
    assert ab.label({"bypass": "off", "ip6": True}) == "off (IPv6)"


class _Scan:
    def __init__(self, v6): self.v6 = v6; self.sampled = None
    def has_ipv6(self): return self.v6
    def looks_cloudflare(self, p): return True
    def scan_target(self, p): return 443, "a.workers.dev"
    def load_ranges(self): return ["1.0.0.0/24"]
    def load_ranges6(self): return ["2606:4700::/32"]
    def sample_ips(self, r, n): self.sampled = list(r); return ["9.9.9.9"]
    def scan(self, ips, port, sni, cb, cancelled=lambda: False): cb("2606:4700::7" if self.v6 else "104.20.1.1", 40, "FRA")


def run(profiles, works, scanner, want=1):
    wins, calls = [], []
    def tester(exe, p, port, timeout=6):
        calls.append((p.get("bypass"), p.get("address_override")))
        return works(p)
    r = ab.auto_run("x", profiles, lambda p, v, ms: wins.append((v, ms)), tester=tester, doh_check=lambda: [],
                    want=want, workers=1, scanner=scanner)
    return r, wins, calls


def test_auto_wins_through_an_ipv6_entry_point(monkeypatch):
    monkeypatch.setattr(ab.socket, "getaddrinfo", lambda *a, **k: [(10, 1, 6, "", ("2606:4700::99", 443, 0, 0))])
    r, wins, calls = run([tls("a")], lambda p: 80 if p.get("address_override") == "2606:4700::99" else -1, _Scan(True))
    assert r["tls"] == 1 and wins[0][0] == {"bypass": "off", "ip6": True}
    assert calls[-1] == ("off", "2606:4700::99")


def test_auto_never_uses_ipv6_when_the_machine_has_no_route(monkeypatch):
    monkeypatch.setattr(ab.socket, "getaddrinfo", lambda *a, **k: [(10, 1, 6, "", ("2606:4700::99", 443, 0, 0))])
    status = []
    ab.auto_run("x", [tls("a")], lambda *a: None, tester=lambda e, p, port, timeout=6: -1, doh_check=lambda: [], want=1,
                workers=1, scanner=_Scan(False), on_status=status.append, relaxed_tester=None)
    assert any("no IPv6 route" in s for s in status)
    seen = []
    ab.auto_run("x", [tls("a")], lambda *a: None, tester=lambda e, p, port, timeout=6: seen.append(p.get("address_override")) or -1,
                doh_check=lambda: [], want=1, workers=1, scanner=_Scan(False), relaxed_tester=None)
    assert not any(a and ":" in a for a in seen)


def test_clean_ip_phase_scans_ipv6_ranges_only_when_available():
    s6, s4 = _Scan(True), _Scan(False)
    run([tls("a")], lambda p: -1, s6)
    run([tls("a")], lambda p: -1, s4)
    assert s6.sampled == ["1.0.0.0/24", "2606:4700::/32"] and s4.sampled == ["1.0.0.0/24"]


def test_clean_ipv6_found_by_the_scan_is_used():
    r, wins, calls = run([tls("a", server="1.2.3.4")], lambda p: 60 if p.get("address_override") == "2606:4700::7" else -1, _Scan(True))
    assert r["tls"] == 1 and wins[0][0]["address_override"] == "2606:4700::7"


def test_xray_config_accepts_an_ipv6_entry_address():
    c = generate_xray_config({**tls("a"), "network": "ws", "host": "a.workers.dev", "path": "/x", "address_override": "2606:4700::99"})
    ob = c["outbounds"][0]
    assert ob["settings"]["vnext"][0]["address"] == "2606:4700::99"
    assert ob["streamSettings"]["tlsSettings"]["serverName"] == "a.workers.dev"
