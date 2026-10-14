from app.utils.leakcheck import analyze, format_report, _p_cf, _p_ipapi
from app.core.browser import build_args

def R(ip, cc, **k): return {"ip": ip, "cc": cc, **k}

def levels(items): return [l for l, _ in items]

def test_all_agree_ok():
    res = {"a": R("1.1.1.1", "DE"), "b": R("1.1.1.1", "DE")}
    assert "ok" in levels(analyze(res)) and "bad" not in levels(analyze(res))

def test_one_db_says_iran_is_bad():
    res = {"a": R("1.1.1.1", "DE"), "b": R("1.1.1.1", "IR")}
    assert "bad" in levels(analyze(res))

def test_disagree_warns():
    res = {"a": R("1.1.1.1", "DE"), "b": R("1.1.1.1", "NL")}
    assert "warn" in levels(analyze(res)) and "bad" not in levels(analyze(res))

def test_no_answer_is_bad():
    assert levels(analyze({"a": None, "b": None})) == ["bad"]

def test_hosting_and_real_ip_leak():
    res = {"ip-api": R("1.1.1.1", "DE", hosting=True)}
    t = " ".join(x for _, x in analyze(res, direct={"ip": "1.1.1.1"}))
    assert "DATACENTER" in t and "REAL IP" in t

def test_tz_and_persian_locale():
    res = {"a": R("1.1.1.1", "DE", tz="Europe/Berlin")}
    t = " ".join(x for _, x in analyze(res, local={"utc_offset_min": 210, "locale": "fa-IR"}))
    assert "time zone" in t and "Persian" in t

def test_parsers():
    assert _p_cf("ip=195.58.38.9\nloc=DE\ncolo=FRA\n")["cc"] == "DE"
    assert _p_ipapi('{"status":"success","query":"1.2.3.4","countryCode":"DE","hosting":true}')["hosting"] is True

def test_format_and_browser_args():
    assert format_report([("ok", "x")]).startswith("[OK]")
    a = build_args("chrome.exe")
    assert "--proxy-server=http://127.0.0.1:10809" in a
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in a

def test_cloudflare_exit_detected():
    res = {"ip-api": R("104.28.1.1", "DE", org="Cloudflare WARP", proxy=True),
           "ipinfo": R("104.28.2.2", "DE", org="AS13335 Cloudflare, Inc."),
           "Cloudflare": R("2a01::1", "DE", org="Cloudflare edge PRG")}
    items = analyze(res)
    txt = " ".join(x for _, x in items)
    assert "CLOUDFLARE" in txt and "Auto/balancer" not in txt and "known VPN/proxy list" not in txt
    assert not any("CLOUDFLARE" in x for l, x in analyze({"a": R("1.1.1.1", "DE", org="Cloudflare edge FRA")}))
