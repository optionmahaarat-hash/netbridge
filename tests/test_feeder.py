import json

import pytest

from app.core import aether, feeder


def test_feeder_config_moves_only_ports(tmp_path):
    src = tmp_path / "active.json"
    src.write_text(json.dumps({"inbounds": [{"tag": "socks-in", "protocol": "socks", "port": 10808},
                                            {"tag": "http-in", "protocol": "http", "port": 10809}],
                               "outbounds": [{"tag": "p0", "protocol": "vless"}], "routing": {"rules": [{"inboundTag": ["socks-in"]}]}}))
    out = tmp_path / "f.json"
    d = feeder.make_feeder_config(src, out, 1901, 1902)
    assert [i["port"] for i in d["inbounds"]] == [1901, 1902] and d["outbounds"][0]["tag"] == "p0"
    assert json.loads(out.read_text()) == d
    assert json.loads(src.read_text())["inbounds"][0]["port"] == 10808          # the original is untouched


def test_feeder_needs_a_socks_inbound(tmp_path):
    src = tmp_path / "a.json"; src.write_text(json.dumps({"inbounds": [{"protocol": "http", "port": 1}]}))
    with pytest.raises(ValueError):
        feeder.make_feeder_config(src, tmp_path / "f.json", 1, 2)


def test_upstream_goes_to_aether_args_and_is_checked():
    a = aether.build_args("a.exe", 1900, tor="tor-only", upstream=feeder.upstream_url(1901))
    assert a[a.index("--upstream") + 1] == "socks5://127.0.0.1:1901"
    assert "--upstream" not in aether.build_args("a.exe", 1900, psiphon="psiphon-only")
    with pytest.raises(ValueError):
        aether.build_args("a.exe", 1900, psiphon="psiphon-only", upstream="ftp://x;rm")
