"""Rebuilds every icon from assets/source/logo-source.png  (dev tool: needs Pillow + numpy)
    python tools/make_icons.py
Outputs: assets/logo.png (full logo, transparent corners), assets/mark.png (symbol only),
         assets/icons/netbridge-<size>.png, assets/netbridge.ico
Small sizes use the symbol only (the text is unreadable at 16-48 px)."""
import io, struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "source" / "logo-source.png"
OUT = ROOT / "assets"
SIZES = [16, 24, 32, 48, 64, 96, 128, 256]
FULL_FROM = 128                       # sizes >= this use the full logo
MARK_BOX = (284, 118, 964, 798)       # square around globe + N + bridge (1254 px source)
BG = (1, 6, 20)


def transparent_corners(im, margin=14):
    """Cut the logo to the neon frame: measure the frame's bounding box and corner radius,
    then apply a smooth rounded-rectangle mask slightly larger than the frame (no halo, no jagged edges)."""
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    bright = a.max(axis=2) > 120                       # the neon frame line
    ys, xs = np.where(bright)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    t = 0                                              # distance along the corner diagonal to the frame
    while not bright[y0 + t, x0 + t]:
        t += 1
    radius = t / (1 - 2 ** -0.5)                       # frame point on the diagonal sits r*(1-1/sqrt2) from each side
    S = 4
    h, w = a.shape[:2]
    m = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        ((x0 - margin) * S, (y0 - margin) * S, (x1 + margin) * S, (y1 + margin) * S),
        radius=int((radius + margin) * S), fill=255)
    out = im.convert("RGBA")
    out.putalpha(m.resize((w, h), Image.LANCZOS))
    return out


def mark_icon(src, size):
    """Symbol on a dark rounded square (works on light and dark taskbars)."""
    big = 512
    crop = src.convert("RGB").crop(MARK_BOX).resize((big, big), Image.LANCZOS)
    mask = Image.new("L", (big * 2, big * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big * 2 - 1, big * 2 - 1), radius=int(big * 2 * 0.22), fill=255)
    mask = mask.resize((big, big), Image.LANCZOS)
    tile = Image.new("RGBA", (big, big), BG + (255,))
    tile.paste(crop, (0, 0))
    tile.putalpha(mask)
    return tile.resize((size, size), Image.LANCZOS)


def write_ico(frames, path):
    """ICO container with PNG-compressed frames (Windows Vista+)."""
    blobs = []
    for im in frames:
        b = io.BytesIO(); im.save(b, "PNG", optimize=True); blobs.append((im.width, b.getvalue()))
    head = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    for w, data in blobs:
        entries += struct.pack("<BBBBHHII", 0 if w >= 256 else w, 0 if w >= 256 else w, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(head + entries + b"".join(d for _, d in blobs))


def main():
    src = Image.open(SRC).convert("RGB")
    full = transparent_corners(src)
    full.resize((1024, 1024), Image.LANCZOS).save(OUT / "logo.png", optimize=True)
    mark_icon(src, 512).save(OUT / "mark.png", optimize=True)
    (OUT / "icons").mkdir(exist_ok=True)
    frames = []
    for s in SIZES:
        im = full.resize((s, s), Image.LANCZOS) if s >= FULL_FROM else mark_icon(src, s)
        im.save(OUT / "icons" / f"netbridge-{s}.png", optimize=True)
        frames.append(im)
    write_ico(frames, OUT / "netbridge.ico")
    print("done:", [p.name for p in sorted(OUT.glob("*.*"))])


if __name__ == "__main__":
    main()
