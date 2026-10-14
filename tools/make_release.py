"""Packs dist/NetBridgeLite/ into release/NetBridgeLite-<version>-win64.zip and writes the signed release/latest.json.
Upload BOTH files to the same folder of your host; the app finds the zip next to latest.json.
   python tools/make_release.py [--notes-fa "..."] [--notes-en "..."] [--dist dist/NetBridgeLite]"""
import argparse, base64, hashlib, json, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cryptography.hazmat.primitives import serialization          # noqa: E402
from app.lite.updater import signed_message                         # noqa: E402
from app.lite.version import APP_ID, LITE_VERSION                   # noqa: E402


def build(dist, out_dir, notes_fa="", notes_en="", key_path=None, version=LITE_VERSION):
    dist, out_dir = Path(dist), Path(out_dir)
    if not (dist / "NetBridgeLite.exe").exists() and not (dist / "NetBridgeLite").exists():
        raise SystemExit(f"{dist} does not contain NetBridgeLite.exe - run build_lite.bat first")
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / f"{APP_ID}-{version}-win64.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(dist.rglob("*")):
            rel = f.relative_to(dist).as_posix()
            if f.is_file() and not rel.startswith(("data/", "updates/")):     # never ship user data
                z.write(f, rel)
    data = zip_path.read_bytes()
    m = {"app": APP_ID, "version": version, "url": zip_path.name, "sha256": hashlib.sha256(data).hexdigest(),
         "size": len(data), "notes": {"fa": notes_fa, "en": notes_en}}
    key = serialization.load_pem_private_key(Path(key_path or ROOT / "keys" / "update_private.key").read_bytes(), None)
    m["signature"] = base64.b64encode(key.sign(signed_message(m))).decode()
    (out_dir / "latest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return zip_path, m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=str(ROOT / "dist" / "NetBridgeLite"))
    ap.add_argument("--notes-fa", default=""); ap.add_argument("--notes-en", default="")
    a = ap.parse_args()
    z, m = build(a.dist, ROOT / "release", a.notes_fa, a.notes_en)
    print(f"Release {m['version']}: {z}  ({m['size'] / 1e6:.1f} MB)\nUpload  {z.name}  and  latest.json  to the same folder.")
