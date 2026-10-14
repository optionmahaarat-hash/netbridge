"""Downloads Xray-core for Windows into cores/xray/.
Usage:  python get_xray.py            -> v26.7.28, but SKIPPED if xray.exe + geo files already exist
        python get_xray.py --force    -> download again even if the files exist
        python get_xray.py v26.8.1    -> any other tag you want (always downloads)
GitHub's "latest" tag lags behind, so a fixed version is used on purpose."""
import io, sys, zipfile, urllib.request
from pathlib import Path

DEFAULT_TAG = "v26.7.28"
DEST = Path("cores/xray")

NEEDED = ("xray.exe", "geoip.dat", "geosite.dat")

def have_all():
    return all((DEST / n).exists() and (DEST / n).stat().st_size > 0 for n in NEEDED)

def main(tag):
    url = f"https://github.com/XTLS/Xray-core/releases/download/{tag}/Xray-windows-64.zip"
    DEST.mkdir(parents=True, exist_ok=True)
    print("Downloading", url)
    data = urllib.request.urlopen(url, timeout=180).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if n.lower() in ("xray.exe", "geoip.dat", "geosite.dat"):
                (DEST / n).write_bytes(z.read(n)); print("  extracted", n)
    print("Done:", (DEST / "xray.exe").resolve())

if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    tags = [a for a in args if not a.startswith("--")]
    if have_all() and not force and not tags:
        print("Xray already installed in", DEST.resolve(), "- skipping download. (use --force to download again)")
        sys.exit(0)
    try: main(tags[0] if tags else DEFAULT_TAG)
    except Exception as e:
        print("FAILED:", e)
        print("If GitHub is blocked, connect Hiddify (System Proxy mode) and run again.")
        sys.exit(1)
