"""Public config lists ("Get free configs"). A source is a plain text/base64 subscription published at one or more mirror addresses
(assets/config_sources.json). The first mirror that answers with usable servers wins. Previous servers of the same group are replaced,
so dead ones from yesterday's list do not pile up. Everything network-related goes through `fetch`, so it is testable."""
import json
from pathlib import Path

SOURCES_FILE = Path(__file__).resolve().parent.parent.parent / "assets" / "config_sources.json"
MAX_PROFILES = 300


class SourceError(Exception):
    pass


def load_sources(path=None):
    try:
        data = json.loads(Path(path or SOURCES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for s in data.get("sources", []):
        mirrors = [m for m in s.get("mirrors", []) if isinstance(m, str) and m.startswith("https://")]
        if s.get("id") and s.get("group") and mirrors:
            out.append({"id": s["id"], "name": s.get("name", s["id"]), "group": s["group"], "page": s.get("page", ""), "mirrors": mirrors})
    return out


def fetch_source(source, fetch, proxy=None):
    """-> (profiles, mirror_used, errors). `fetch(url, proxy=...)` returns (profiles, errors) like utils.subscription.fetch_subscription."""
    last = "no mirror answered"
    for url in source["mirrors"]:
        try:
            profiles, errors = fetch(url, proxy=proxy)
        except Exception as e:
            last = f"{url}: {e}"
            continue
        if profiles:
            return profiles[:MAX_PROFILES], url, errors
        last = f"{url}: the list has no usable servers"
    raise SourceError(last)


def drop_group(profiles, group):
    """The profile list without the old servers of `group` (they are replaced by the fresh list)."""
    return [p for p in profiles if p.get("group") != group]


def due(last, now, hours=24):
    """True when the list was never fetched, or the last fetch is at least `hours` old (a clock set backwards also counts as due)."""
    try:
        return not last or now < last or now - last >= hours * 3600
    except TypeError:
        return True
