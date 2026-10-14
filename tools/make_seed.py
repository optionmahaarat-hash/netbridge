"""Creates assets/seed_profiles.json = the servers every NEW installation starts with.
Source: data/profiles.json (your own list). Old speed measurements are dropped (they are meaningless on another PC).
   python tools/make_seed.py [path/to/profiles.json]"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DROP = ("delay", "delay_ts", "tls_tried", "pin_failed")


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "profiles.json"
    out = ROOT / "assets" / "seed_profiles.json"
    if not src.exists():
        if out.exists():
            print("No", src, "- keeping the existing", out.name); return
        print("No", src, "- the installer will start with an empty server list"); return
    data = json.loads(src.read_text(encoding="utf-8"))
    seed = [{k: v for k, v in p.items() if k not in DROP} for p in data if isinstance(p, dict)]
    out.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(seed)} servers -> {out}")


if __name__ == "__main__":
    main()
