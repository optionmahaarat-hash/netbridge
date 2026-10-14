from app.utils.parser import parse_many

def test_vless():
    p, e = parse_many("vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?type=ws&security=tls#A")
    assert len(p) == 1 and not e and p[0]["type"] == "vless"

def test_trojan():
    p, e = parse_many("trojan://pass@example.com:443?security=tls#A")
    assert p[0]["type"] == "trojan"

def test_vmess():
    import base64, json
    raw = {"ps":"A","add":"example.com","port":"443","id":"123e4567-e89b-12d3-a456-426614174000","net":"ws","tls":"tls"}
    uri = "vmess://" + base64.b64encode(json.dumps(raw).encode()).decode()
    p, e = parse_many(uri)
    assert p[0]["type"] == "vmess"
