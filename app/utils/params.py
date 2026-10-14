from urllib.parse import unquote

def extract_extra(q):
    """Extra share-link params: PattNG (cs, fm) + insecure, Reality, gRPC."""
    get = lambda k: unquote(q.get(k, [""])[0])
    out = {}
    for src, dst in [("cs", "cs"), ("fm", "fm"), ("pbk", "pbk"), ("sid", "sid"),
                     ("spx", "spx"), ("serviceName", "service_name"), ("pcs", "pcs"), ("ech", "ech"), ("mode", "xmode")]:
        if get(src): out[dst] = get(src)
    if any(get(k) == "1" for k in ("insecure", "allowInsecure", "allow_insecure")):
        out["insecure"] = True
    if out.get("cs") or out.get("fm"):
        out["bypass"] = "custom"   # link already carries its own settings
    return out
