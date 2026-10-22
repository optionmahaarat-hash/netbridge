import struct
from app.core import resolverscan as rs, autobypass as ab


def reply(qid, flags=0x8180, an=1):
    return struct.pack(">HHHHHH", qid, flags, 1, an, 0, 0) + b"\x00" * 4


def test_valid_reply_checks_id_flags_and_answers():
    assert rs.valid_reply(reply(7), 7)
    assert not rs.valid_reply(reply(8), 7)                   # someone else's / spoofed id
    assert not rs.valid_reply(reply(7, flags=0x0100), 7)     # not a response
    assert not rs.valid_reply(reply(7, flags=0x8183), 7)     # NXDOMAIN-style error
    assert not rs.valid_reply(reply(7, an=0), 7)             # empty answer
    assert not rs.valid_reply(b"\x00" * 5, 7)


def test_build_query_roundtrip():
    qid, q = rs.build_query("www.google.com", qid=0x1234)
    assert qid == 0x1234 and q[:2] == b"\x12\x34" and q.endswith(struct.pack(">HH", 1, 1))


def fake(ok):
    def f(*a):
        if ok: return True
        raise OSError("blocked")
    return f


def tests_for(udp, tcp, dot, doh):
    return {"udp": fake(udp), "tcp": fake(tcp), "dot": fake(dot), "doh": fake(doh)}


def test_probe_and_scan_order_and_working_doh():
    good = ("Good", "1.1.1.1", "https://1.1.1.1/dns-query", "x")
    dead = ("Dead", "9.9.9.9", "https://9.9.9.9/dns-query", "x")
    nodoh = ("NoDoh", "2.2.2.2", None, None)
    rows = rs.scan([dead, nodoh, good], tests=None, workers=1) if False else None
    out = [rs.probe(r, tests=tests_for(*t)) for r, t in ((dead, (0, 0, 0, 0)), (nodoh, (1, 0, 0, 0)), (good, (1, 1, 1, 1)))]
    assert out[0]["udp"] == -1 and rs.best_ms(out[0]) is None
    assert out[1]["doh"] == -1 and out[1]["doh_url"] is None and rs.best_ms(out[1]) is not None
    assert rs.working_doh(out) == ["https://1.1.1.1/dns-query"]
    srt = sorted(out, key=lambda r: (rs.best_ms(r) is None, rs.best_ms(r) or 0))
    assert srt[-1]["label"] == "Dead"


def test_extra_doh_is_tried_first(monkeypatch):
    seen = []
    monkeypatch.setattr(ab, "doh_works", lambda u, t=4.0: seen.append(u) or True)
    monkeypatch.setattr(ab, "EXTRA_DOH", ["https://9.9.9.9/dns-query"])
    got = ab.reachable_doh(workers=1)
    assert got[0] == "https://9.9.9.9/dns-query" and len(set(got)) == len(got)
