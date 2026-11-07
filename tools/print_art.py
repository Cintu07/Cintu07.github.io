"""Print-style art for the site: cream shapes cut out of a washed blue block, like a two-colour
relief print. Every piece is saved as an alpha mask (ink = opaque), so the page paints it with its own
colours and the same file works on cream by day and on navy at night.

    python tools/print_art.py            # writes assets/print/*.png

Nine motifs, all thresholded noise shaped by a field: swirl, trail, rays, streaks, strokes, spray,
clouds, reflection, ripples. A post's panel is one motif seeded by its slug, so it never changes.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "print"


def noise(h, w, cell, rng):
    """smooth value noise in [0, 1]: a random grid, upsampled bicubically"""
    gh, gw = max(2, int(h / cell) + 3), max(2, int(w / cell) + 3)
    g = Image.fromarray((rng.random((gh, gw)) * 255).astype(np.uint8))
    big = g.resize((int(gw * cell), int(gh * cell)), Image.BICUBIC)
    return np.asarray(big, dtype=np.float32)[:h, :w] / 255.0


def fbm(h, w, cell, rng, octaves=4):
    out, amp, total = np.zeros((h, w), np.float32), 1.0, 0.0
    for _ in range(octaves):
        out += noise(h, w, cell, rng) * amp
        total += amp
        amp *= 0.5
        cell = max(2, cell / 2)
    return out / total


def streaked(h, w, cell, stretch, angle, rng, octaves=3):
    """noise drawn out along one direction: made on a wide canvas squashed in x, stretched back, turned"""
    d = int(np.hypot(h, w)) + 8
    base = fbm(d, max(2, int(d / stretch)), cell / stretch, rng, octaves)
    img = Image.fromarray((base * 255).astype(np.uint8)).resize((d, d), Image.BICUBIC).rotate(angle, Image.BICUBIC)
    top, left = (d - h) // 2, (d - w) // 2
    return np.asarray(img, np.float32)[top:top + h, left:left + w] / 255.0


def grid(h, w):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return x / w, y / h


def motif(name, h, w, rng):
    """returns the cream shapes: 1 where the paper shows through"""
    x, y = grid(h, w)
    s = min(h, w)
    n = fbm(h, w, s / 5, rng)
    fine = fbm(h, w, s / 22, rng, 3)
    if name == "swirl":
        cx, cy = 0.38 + rng.random() * 0.1, 0.55
        d = np.hypot((x - cx) * w / s, (y - cy) * h / s) + (n - 0.5) * 0.12
        a = np.arctan2(y - cy, x - cx)
        # a whole turn of the angle must move the phase by a whole number of rings, or the spiral
        # shows a seam where the angle wraps from -pi to pi
        rings = np.sin(d * 46 + a) > 0.82 + (fine - 0.5) * 0.9
        core = (d < 0.12 + (n - 0.5) * 0.1) & (fine > 0.45)
        beads = (np.sin(d * 46) > 0.4) & (fine > 0.68)
        return rings | core | beads
    if name == "trail":
        t = np.linspace(0, 1, 26)
        px = 0.3 + 0.45 * t + 0.08 * np.sin(t * 7 + rng.random() * 6)
        py = 1.0 - t * 0.95
        m = np.zeros((h, w), bool)
        for i, (a, b) in enumerate(zip(px, py)):
            for k in range(2):
                ox, oy = a + (k - 0.5) * 0.05, b + rng.normal() * 0.01
                rx, ry = (0.022 + rng.random() * 0.012) * (1 - t[i] * 0.4), 0.012 + rng.random() * 0.006
                m |= (((x - ox) / rx) ** 2 + ((y - oy) / ry) ** 2 + (fine - 0.5) * 0.9) < 1
        return m
    if name == "rays":
        cx, cy = 1.02, -0.05
        a = np.arctan2((y - cy) * h, (x - cx) * w)
        d = np.hypot((x - cx) * w / s, (y - cy) * h / s)
        spokes = np.cos(a * 22 + (n - 0.5) * 1.2) > 0.86 - d * 0.05
        return (spokes & (d > 0.08)) | (d < 0.3 + (n - 0.5) * 0.06)
    if name == "streaks":
        u = (x * w - y * h * 0.9) / s
        lanes = np.sin(u * 20 + (n - 0.5) * 2) > 0.93
        beads = (np.sin(u * 20) > 0.6) & (fine > 0.66)
        return lanes | beads
    if name == "strokes":
        st = streaked(h, w, s / 4, 7, 38, rng)
        return st + (fine - 0.5) * 0.15 > 0.66
    if name == "spray":
        edge = x + (n - 0.5) * 0.6 + (fine - 0.5) * 0.25 > 0.78
        dots = (rng.random((h, w)) > 0.9965)
        dots = np.asarray(Image.fromarray(dots.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(5))) > 0
        return edge | (dots & (x > 0.15)) | ((fbm(h, w, s / 14, rng, 2) > 0.74) & (x > 0.45))
    if name == "clouds":
        warp = fbm(h, w, s / 3, rng)
        c = fbm(h, w, s / 3.2, rng) + (warp - 0.5) * 0.35 + (fine - 0.5) * 0.25
        return c > 0.5
    if name == "reflection":
        st = streaked(h, w, s / 9, 9, 0, rng)
        col = np.abs(x - 0.5 - (noise(h, w, s / 2, rng) - 0.5) * 0.25) * w / s
        return st - col * 0.9 + (y - 0.5) * 0.15 > 0.42
    if name == "ripples":
        st = streaked(h, w, s / 8, 10, 0, rng)
        return st + (y - 0.5) * 0.3 + (fine - 0.5) * 0.1 > 0.6
    raise ValueError(name)


MOTIFS = ["swirl", "trail", "rays", "streaks", "strokes", "spray", "clouds", "reflection", "ripples"]


def ink(shapes, rng, edge_rough=True):
    """the blue block: opaque except where the shapes are, slightly uneven like a hand-inked block"""
    h, w = shapes.shape
    m = shapes.astype(np.float32)
    if edge_rough:
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
        m = (m + (noise(h, w, 3, rng) - 0.5) * 0.5 > 0.5).astype(np.float32)
    alpha = 1 - m
    alpha *= 0.86 + 0.14 * fbm(h, w, min(h, w) / 2, rng, 2)      # uneven ink
    return alpha


def save(alpha, name):
    OUT.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(np.clip(alpha * 255, 0, 255).astype(np.uint8), "L")
    rgba = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rgba.putalpha(img)
    rgba.save(OUT / f"{name}.png", optimize=True)


def seed_of(text):
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)


def tiles(size=600, gap=10, seed=7):
    """the nine motifs as a 3 x 3 sheet, gaps left as paper"""
    rng = np.random.default_rng(seed)
    cell = (size - 2 * gap) // 3
    sheet = np.zeros((size, size), np.float32)
    for i, name in enumerate(MOTIFS):
        r, c = divmod(i, 3)
        sheet[r * (cell + gap): r * (cell + gap) + cell, c * (cell + gap): c * (cell + gap) + cell] = ink(motif(name, cell, cell, rng), rng)
    return sheet


BAYER = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38],
                  [60, 28, 52, 20, 62, 30, 54, 22], [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                  [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], np.float32) / 64


def dissolve(alpha, fade, dot=3):
    """fades ink out as a halftone: ordered dots, the way a print loses its edge"""
    h, w = alpha.shape
    t = np.kron(BAYER, np.ones((dot, dot), np.float32))
    t = np.tile(t, (h // t.shape[0] + 1, w // t.shape[1] + 1))[:h, :w]
    return alpha * (fade > t)


def corner(w=900, h=1100, seed=11):
    """the big piece that fades in at the bottom right of the home page: clouds over water"""
    rng = np.random.default_rng(seed)
    top = motif("clouds", h, w, rng)
    low = motif("ripples", h, w, rng)
    x, y = grid(h, w)
    shapes = np.where(y < 0.6 + (noise(h, w, 120, rng) - 0.5) * 0.06, top, low)
    alpha = ink(shapes, rng)
    fade = np.clip((x - 0.0) / 0.6, 0, 1) * np.clip((y - 0.0) / 0.42, 0, 1)
    fade = np.clip(fade + (fbm(h, w, 90, rng, 3) - 0.5) * 0.35, 0, 1)
    return dissolve(alpha, fade)


def panel(slug, w=1200, h=420):
    rng = np.random.default_rng(seed_of(slug))
    name = MOTIFS[seed_of(slug + "#") % len(MOTIFS)]
    return ink(motif(name, h, w, rng), rng), name


def main():
    save(tiles(), "tiles")
    save(corner(), "corner")
    posts = sorted(p.stem for p in (ROOT / "content" / "posts").glob("*.md"))
    made = {}
    for slug in posts:
        alpha, name = panel(slug)
        save(alpha, f"post-{slug}")
        made[slug] = name
    for name in MOTIFS:   # one of each, for pages without a post
        rng = np.random.default_rng(seed_of(name))
        save(ink(motif(name, 420, 1200, rng), rng), f"motif-{name}")
    (OUT / "manifest.json").write_text(json.dumps(made, indent=1))
    print(f"wrote {len(posts)} post panels, the tile sheet and the corner piece to {OUT}")


if __name__ == "__main__":
    main()
