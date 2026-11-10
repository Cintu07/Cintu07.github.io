"""Makes a figure's paper background transparent so it sits on the blog's own sheet (and inverts
cleanly in dark mode). It is colour-to-alpha, the way GIMP does it: each pixel is read as ink laid
over the background colour, and only the background's share is taken out, so anti-aliased edges and
soft colours stay smooth instead of keeping a white fringe.

    python tools/transparent.py assets/img/a630/fig-01.png [more files...]   (png or webp, in place;
    a png's .webp twin, if there is one, is regenerated)
"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image


def background_of(rgb):
    # the colour of the four corners, which on a figure is the paper
    h, w, _ = rgb.shape
    corners = np.array([rgb[2, 2], rgb[2, w - 3], rgb[h - 3, 2], rgb[h - 3, w - 3]], dtype=np.float64)
    return np.median(corners, axis=0)


def colour_to_alpha(rgba, bg):
    rgb = rgba[..., :3].astype(np.float64) / 255.0
    bg = bg / 255.0
    # how far each channel is from the background, as a share of how far it could go
    room = np.where(rgb >= bg, 1.0 - bg, bg)
    room = np.where(room == 0, 1.0, room)
    alpha = np.max(np.abs(rgb - bg) / room, axis=-1)
    safe = np.where(alpha == 0, 1.0, alpha)[..., None]
    ink = (rgb - bg) / safe + bg
    out = np.empty(rgba.shape, dtype=np.uint8)
    out[..., :3] = np.clip(np.round(ink * 255), 0, 255)
    out[..., 3] = np.clip(np.round(alpha * (rgba[..., 3] / 255.0) * 255), 0, 255)
    return out


def main():
    for name in sys.argv[1:]:
        path = Path(name)
        img = Image.open(path).convert("RGBA")
        rgba = np.asarray(img)
        bg = background_of(rgba[..., :3])
        out = Image.fromarray(colour_to_alpha(rgba, bg), "RGBA")
        if path.suffix == ".webp":
            out.save(path, "WEBP", quality=92, method=6)
        else:
            out.save(path, "PNG", optimize=True)
            twin = path.with_suffix(".webp")
            if twin.exists():
                out.save(twin, "WEBP", quality=90, method=6)
        print(f"{path}: background {tuple(int(x) for x in bg)} is now transparent")


if __name__ == "__main__":
    main()
