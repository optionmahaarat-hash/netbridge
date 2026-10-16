"""edgetunnel-style "exit" choice carried in the WebSocket path.

A Cloudflare Worker such as cmliu/edgetunnel reads, from the request URL, how it should reach the final site:
    ?proxyip=host[:port]                 reach sites through this ProxyIP (for Cloudflare-hosted targets)
    ?socks5=[user:pass@]host:port        send the traffic out through a SOCKS5 proxy
    ?http=[user:pass@]host:port          ... or an HTTP proxy
(the README also shows the /proxyip=... path form; this app uses the query form, which the README lists too)

The profile stores it as   worker_exit = "proxyip=1.2.3.4:443"   and it is appended to the path when the config is built.
The text goes into a URL, so it is checked against a strict character set first.
"""
import re

KEYS = ("proxyip", "socks5", "http")
_VALUE = re.compile(r"^[A-Za-z0-9._:@\-\[\]%+]{1,200}$")      # no spaces, '&', '?', '#', '/', '='


def parse(spec):
    """'proxyip=1.2.3.4:443' -> ('proxyip', '1.2.3.4:443'). Raises ValueError with a plain reason."""
    spec = (spec or "").strip().lstrip("/?&")
    if "=" not in spec:
        raise ValueError("use one of: proxyip=host:port, socks5=user:pass@host:port, http=host:port")
    key, val = spec.split("=", 1)
    key = key.strip().lower()
    if key not in KEYS:
        raise ValueError(f"'{key}' is not supported (use proxyip, socks5 or http)")
    if not _VALUE.match(val):
        raise ValueError("the value may only contain letters, digits and . : @ - _ [ ] % +")
    return key, val


def normalize(spec):
    """Validated 'key=value' text, or '' for an empty spec. Raises ValueError."""
    if not (spec or "").strip():
        return ""
    k, v = parse(spec)
    return f"{k}={v}"


def apply(path, spec):
    """The path with the exit appended as a query parameter. An invalid or empty spec leaves the path alone.
    Any proxyip/socks5/http already in the path is replaced, so the profile's choice always wins."""
    path = path or "/"
    try:
        spec = normalize(spec)
    except ValueError:
        return path
    if not spec:
        return path
    base, _, query = path.partition("?")
    keep = [q for q in query.split("&") if q and q.split("=", 1)[0].lower() not in KEYS]
    base = re.sub(r"/(?:proxyip|socks5|http)=[^/?]*", "", base) or "/"
    return base + "?" + "&".join(keep + [spec])
