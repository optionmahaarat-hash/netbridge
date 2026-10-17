import json
import pytest
from app.core import sources as S


def test_bundled_sources_file_is_valid_and_https_only():
    srcs = S.load_sources()
    assert srcs and srcs[0]["id"] == "patterniha" and len(srcs[0]["mirrors"]) >= 2
    assert all(m.startswith("https://") for s in srcs for m in s["mirrors"]) and srcs[0]["group"]


def test_loader_ignores_bad_entries(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"sources": [{"id": "a", "group": "G", "mirrors": ["http://x", "https://ok/1"]}, {"id": "b", "mirrors": ["https://x"]}, {"group": "G"}]}))
    assert [s["id"] for s in S.load_sources(f)] == ["a"] and S.load_sources(f)[0]["mirrors"] == ["https://ok/1"]
    assert S.load_sources(tmp_path / "missing.json") == []


def test_first_working_mirror_wins_and_failures_fall_through():
    src = {"mirrors": ["https://a/1", "https://b/2", "https://c/3"]}
    calls = []

    def fetch(url, proxy=None):
        calls.append(url)
        if url.endswith("/1"): raise OSError("blocked")
        if url.endswith("/2"): return [], []                    # reachable but empty
        return [{"server": "x"}] * 5, ["bad line"]
    profiles, used, errors = S.fetch_source(src, fetch)
    assert used == "https://c/3" and len(profiles) == 5 and errors == ["bad line"] and calls == ["https://a/1", "https://b/2", "https://c/3"]


def test_all_mirrors_failing_gives_the_last_reason_and_cap_applies():
    with pytest.raises(S.SourceError, match="blocked"):
        S.fetch_source({"mirrors": ["https://a/1"]}, lambda u, proxy=None: (_ for _ in ()).throw(OSError("blocked")))
    big = S.fetch_source({"mirrors": ["https://a"]}, lambda u, proxy=None: ([{"i": i} for i in range(1000)], []))[0]
    assert len(big) == S.MAX_PROFILES


def test_drop_group_only_removes_that_group():
    ps = [{"group": "Free: patterniha", "n": 1}, {"group": "My Worker", "n": 2}, {"n": 3}]
    assert [p["n"] for p in S.drop_group(ps, "Free: patterniha")] == [2, 3]
