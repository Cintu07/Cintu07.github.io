"""Turns the pictures listed in content/gallery.json into web images in assets/gallery/.

    python tools/gallery.py [source folder]        # default: ~/Downloads

Each picture gets a large WebP (animated if the source moves) and a small still for the grid.
Their sizes go to assets/gallery/manifest.json, so the page reserves the space before they load.
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "gallery"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads"
BIG, SMALL = 1400, 640


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def fit(img, limit):
    img = img.convert("RGBA") if img.mode in ("P", "LA", "RGBA") else img.convert("RGB")
    if max(img.size) > limit:
        img.thumbnail((limit, limit), Image.LANCZOS)
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = json.loads((ROOT / "content" / "gallery.json").read_text(encoding="utf-8"))
    manifest = {}
    for e in entries:
        name = slug(e["title"])
        src = Image.open(SRC / e["file"])
        moving = getattr(src, "is_animated", False) and src.n_frames > 1
        if moving:
            frames, durations = [], []
            for frame in ImageSequence.Iterator(src):
                frames.append(fit(frame.copy(), 900))
                durations.append(frame.info.get("duration", 80))
            frames[0].save(OUT / f"{name}.webp", save_all=True, append_images=frames[1:], duration=durations, loop=0, quality=72, method=5)
            still = frames[0]
            # pixel art keeps its palette better, and smaller, as the original gif: keep whichever is lighter
            original = SRC / e["file"]
            if original.suffix.lower() == ".gif" and original.stat().st_size < (OUT / f"{name}.webp").stat().st_size:
                (OUT / f"{name}.webp").unlink()
                (OUT / f"{name}.gif").write_bytes(original.read_bytes())
        else:
            still = fit(src, BIG)
            still.save(OUT / f"{name}.webp", quality=84, method=6)
        small = fit(still, SMALL)
        small.save(OUT / f"{name}-s.webp", quality=80, method=6)
        big = OUT / f"{name}.gif" if (OUT / f"{name}.gif").exists() else OUT / f"{name}.webp"
        manifest[name] = {"w": still.width, "h": still.height, "sw": small.width, "sh": small.height, "moving": moving, "big": big.name}
        print(f"{name:28} {still.width}x{still.height} {'moving' if moving else ''} {big.name} {big.stat().st_size // 1024} KB")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
