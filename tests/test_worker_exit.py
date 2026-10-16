import pytest

from app.core import worker_exit as we
from app.core.config_generator import generate_xray_config


def test_parse_and_normalize():
    assert we.parse("proxyip=1.2.3.4:443") == ("proxyip", "1.2.3.4:443")
    assert we.normalize("  /?SOCKS5=user:pa-ss@host.example:1080 ") == "socks5=user:pa-ss@host.example:1080"
    assert we.normalize("") == "" and we.normalize(None) == ""
    for bad in ("1.2.3.4", "foo=bar", "proxyip=a b", "proxyip=a&b=c", "socks5=x/y", "http=a#b", "proxyip=" + "a" * 300):
        with pytest.raises(ValueError):
            we.normalize(bad)


def test_apply_to_paths():
    assert we.apply("/", "proxyip=1.2.3.4:443") == "/?proxyip=1.2.3.4:443"
    assert we.apply("/ws?ed=2560", "socks5=u:p@h:1") == "/ws?ed=2560&socks5=u:p@h:1"
    assert we.apply("/ws?proxyip=old&ed=1", "proxyip=new") == "/ws?ed=1&proxyip=new"      # profile's choice replaces
    assert we.apply("/proxyip=old", "http=h:8080") == "/?http=h:8080"
    assert we.apply("/a", "") == "/a" and we.apply("/a", "garbage") == "/a" and we.apply("", "") == "/"


def _vless(**kw):
    return {"type": "vless", "name": "a", "server": "x.example", "port": 443, "uuid": "11111111-1111-1111-1111-111111111111",
            "security": "tls", "network": "ws", "path": "/?ed=2560", "host": "h.example", "sni": "h.example", **kw}


def _ws_path(cfg):
    for o in cfg["outbounds"]:
        ws = o.get("streamSettings", {}).get("wsSettings")
        if ws:
            return ws["path"]


def test_config_gets_the_exit_in_ws_path():
    assert _ws_path(generate_xray_config(_vless(worker_exit="proxyip=9.9.9.9:443"))) == "/?ed=2560&proxyip=9.9.9.9:443"
    assert _ws_path(generate_xray_config(_vless())) == "/?ed=2560"
    assert _ws_path(generate_xray_config(_vless(worker_exit="bad value"))) == "/?ed=2560"
