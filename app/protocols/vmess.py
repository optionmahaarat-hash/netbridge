import base64, json
from urllib.parse import unquote

def parse_vmess(uri):
    raw = uri.strip()[len("vmess://"):]
    raw += "=" * (-len(raw) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(raw).decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid VMess URI: {e}")
    net = data.get("net", "tcp") or "tcp"
    extra = {}
    if net == "grpc":
        extra["service_name"] = data.get("path", "")        # vmess links keep the gRPC service name in "path"
    elif net in ("xhttp", "splithttp") and data.get("mode"):
        extra["xmode"] = data["mode"]
    return {
        **extra,
        "name": data.get("ps") or f"{data.get('add')}:{data.get('port')}",
        "type": "vmess",
        "server": str(data.get("add", "")).strip(),
        "port": int(str(data.get("port", 0)).strip() or 0),
        "uuid": data.get("id", ""),
        "network": net,
        "security": data.get("tls", ""),
        "sni": data.get("sni", ""),
        "host": data.get("host", ""),
        "path": data.get("path", ""),
        "fp": data.get("fp", ""),
        "alpn": data.get("alpn", ""),
    }
