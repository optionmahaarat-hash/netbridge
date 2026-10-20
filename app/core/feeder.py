"""A second, hidden Xray that keeps the CURRENT working connection alive for Aether to dial through (--upstream).

Why: on a network that blocks Psiphon's / Tor's / WARP's own start-up traffic, Aether can still start when its dialling goes through a
proxy that already works. The main Xray is then restarted onto Aether's own SOCKS port, so Aether needs a separate Xray that keeps
the old route; otherwise Aether would dial through itself. Only local ports change: outbounds, routing and DNS stay as they were."""
import json
from pathlib import Path


def make_feeder_config(active_path, out_path, socks_port, http_port):
    """Copies the active Xray config, moving its local SOCKS/HTTP inbounds to the given ports. Returns the new dict."""
    data = json.loads(Path(active_path).read_text(encoding="utf-8"))
    n = 0
    for ib in data.get("inbounds", []):
        if ib.get("protocol") == "socks":
            ib["port"] = int(socks_port); n += 1
        elif ib.get("protocol") in ("http", "mixed"):
            ib["port"] = int(http_port)
    if not n:
        raise ValueError("the active config has no SOCKS inbound")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def upstream_url(socks_port):
    return f"socks5://127.0.0.1:{int(socks_port)}"
