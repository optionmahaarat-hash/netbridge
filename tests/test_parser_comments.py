from app.utils.parser import parse_many

RAW = """#profile-title: vip101
vless://9c11bdf9-b1ac-4a3b-88da-632ff0484337@145.239.65.118:20138?encryption=none&security=none&type=ws&path=%2Fkb-ws#katabump
ss://9c11bdf9-b1ac-4a3b-88da-632ff0484337@145.239.65.118:20138?encryption=none&security=none&type=ws&path=%2Fkb-ws#katabump
"""

def test_comment_header_is_ignored_and_plain_vless_ws_parsed():
    profiles, errors = parse_many(RAW)
    assert len(profiles) == 1 and profiles[0]["security"] == "none" and profiles[0]["network"] == "ws"
    assert profiles[0]["path"] == "/kb-ws" and profiles[0]["port"] == 20138
    assert len(errors) == 1 and "Shadowsocks" in errors[0][1]          # the malformed ss:// line (uuid as credentials)
