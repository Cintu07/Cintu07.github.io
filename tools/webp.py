"""A WebP beside every large picture in assets/img and assets/books, for the pages to offer first.

    python tools/webp.py

Diagrams are flat colour, so they are tried lossless first (sharp lines, often a fifth of the png).
If lossless does not save at least 30 percent, a high-quality lossy one is made instead. A WebP that is
not clearly smaller than the original is not kept, and the page keeps using the original.
"""
import io
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MIN_BYTES = 40_000


def encode(img, **kw):
    buf = io.BytesIO()
    img.save(buf, "WEBP", **kw)
    return buf.getvalue()


def main():
    saved = 0
    for path in sorted([*(ROOT / "assets" / "img").rglob("*"), *(ROOT / "assets" / "books").rglob("*")]):
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg") or path.stat().st_size < MIN_BYTES:
            continue
        size = path.stat().st_size
        img = Image.open(path)
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
        best = encode(img, lossless=True, method=6) if path.suffix.lower() == ".png" else None
        if best is None or len(best) > 0.7 * size:
            lossy = encode(img, quality=86, method=6)
            if best is None or len(lossy) < len(best):
                best = lossy
        target = path.with_suffix(".webp")
        if len(best) < 0.85 * size:
            target.write_bytes(best)
            saved += size - len(best)
            print(f"{path.relative_to(ROOT)}  {size // 1024} KB -> {len(best) // 1024} KB")
        elif target.exists():
            target.unlink()
    print(f"saved {saved / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
