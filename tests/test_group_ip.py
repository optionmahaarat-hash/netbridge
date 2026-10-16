from app.core import ipscan


def P(name, group, port=443, sec="tls", **kw):
    return {"name": name, "group": group, "port": port, "security": sec, **kw}


def sample():
    return [P("a1", "A"), P("a2", "A"), P("a3", "A", port=8080), P("a4", "A", sec="none"), P("b1", "B"), P("b2", "B")]


def test_group_scope_and_roundrobin():
    ps = sample()
    ch = ipscan.spread_clean_ips(ps, ["1.1.1.1", "2.2.2.2"], "A")
    assert [q["name"] for q in ch] == ["a1", "a2"]
    assert ps[0]["address_override"] == "1.1.1.1" and ps[1]["address_override"] == "2.2.2.2"
    assert all("address_override" not in q for q in ps[2:])          # non-CF and other group untouched


def test_wraps_around_and_empty_list_noop():
    ps = [P(f"x{i}", "G") for i in range(5)]
    ipscan.spread_clean_ips(ps, ["1.1.1.1", "2.2.2.2"], "G")
    assert [q["address_override"] for q in ps] == ["1.1.1.1", "2.2.2.2", "1.1.1.1", "2.2.2.2", "1.1.1.1"]
    assert ipscan.spread_clean_ips(sample(), [], "A") == []


def test_all_groups_when_empty_group():
    ps = sample()
    assert len(ipscan.spread_clean_ips(ps, ["9.9.9.9"], "")) == 4


def test_clear_only_group():
    ps = sample()
    ipscan.spread_clean_ips(ps, ["1.1.1.1"], "")
    assert ipscan.clear_clean_ips(ps, "B") == 2
    assert ps[0]["address_override"] == "1.1.1.1" and "address_override" not in ps[4]
    assert ipscan.clear_clean_ips(ps, "") == 2
