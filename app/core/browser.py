"""Open Chrome / Edge in a separate profile that cannot leak your location.

- uses the NetBridge HTTP proxy directly (no dependency on Windows system proxy)
- WebRTC may only use the proxy (no STUN request that reveals your real IP)
- language en-US (no Accept-Language: fa)
- its own profile folder: no Iranian cookies/accounts, location permission starts as 'ask'
"""
import os
import shutil
import subprocess
from pathlib import Path

PROFILE_DIR = Path("data/clean-browser")


def find_browser():
    pf = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")]
    rel = [r"Google\Chrome\Application\chrome.exe",
           r"Microsoft\Edge\Application\msedge.exe",
           r"BraveSoftware\Brave-Browser\Application\brave.exe"]
    for base in filter(None, pf):
        for r in rel:
            p = Path(base) / r
            if p.exists():
                return str(p)
    for name in ("chrome", "msedge", "brave", "google-chrome", "chromium"):
        p = shutil.which(name)
        if p:
            return p
    return None


def build_args(exe, http_port=10809, profile=PROFILE_DIR, url="https://www.cloudflare.com/cdn-cgi/trace"):
    return [exe,
            f"--user-data-dir={Path(profile).resolve()}",
            f"--proxy-server=http://127.0.0.1:{http_port}",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--lang=en-US", "--accept-lang=en-US,en",
            "--no-first-run", "--no-default-browser-check",
            url]


def launch(http_port=10809):
    exe = find_browser()
    if not exe:
        raise FileNotFoundError("Chrome / Edge / Brave not found.")
    Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)
    subprocess.Popen(build_args(exe, http_port))
    return exe
