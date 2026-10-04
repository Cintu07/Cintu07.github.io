"""Cuts the background out of a picture and saves it as a webp with real transparency.

    python tools/cutout.py oyster=~/Downloads/asset.jpeg horse=~/Downloads/asset2.jpeg
    python tools/cutout.py shell.jpeg --mode photo --tolerance 0.22
    python tools/cutout.py busy-photo.jpg --engine rembg

The result goes to assets/art/<name>.webp, cropped to the subject, and assets/art/manifest.json
records its size and whether it is ink, which is what the site build reads.

Two kinds of picture need two different cuts, and the tool picks by looking at the picture:

  ink    black on paper: line art, engravings, silhouettes. Nothing is "removed". The paper's own
         brightness, followed across the page so a grey vignette or a gradient is handled, is divided
         out, and what is left is how much ink there is at each pixel. That becomes the alpha channel
         over a black fill, so a fine line stays fine, a soft shadow stays soft, and the same file sits
         on white or, flipped, on a dark page.

  photo  a coloured subject on a plain background. The background is whatever looks like it and is
         connected to the picture's edge, so a bright highlight inside the subject is never cut out.
         A narrow band at the boundary is left undecided, and closed-form matting (pymatting) solves
         the alpha inside it, hair and soft edges included. Then the subject's true colour is
         recovered at those edge pixels, which is what removes the white halo a plain mask leaves.

  --engine rembg  is for a busy background that these cannot read: a neural model finds the subject
         and matting refines the edge. It needs `pip install rembg` and a model on first use.

    pip install pillow numpy scipy pymatting
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent.parent
GRID8 = np.ones((3, 3), bool)


def luminance(rgb):
    return rgb @ np.array([0.2126, 0.7152, 0.0722])


def border_ring(h, w, t):
    ring = np.zeros((h, w), bool)
    ring[:t], ring[-t:], ring[:, :t], ring[:, -t:] = True, True, True, True
    return ring


def estimate_background(rgb):
    """the colour of the picture's background, from the brightest half of its border. the subject may
    run off one or two edges, so the border is not all background and the median alone would be wrong"""
    h, w, _ = rgb.shape
    px = rgb[border_ring(h, w, max(2, round(0.01 * max(h, w))))]
    keep = px[luminance(px) >= np.median(luminance(px))]
    return np.median(keep, axis=0), float(keep.std(axis=0).mean())


def how_much_ink(rgb):
    """0 where the page is bare, 1 where it is solid ink, with the page's own brightness divided out"""
    h, w, _ = rgb.shape
    lum = luminance(rgb)
    sigma = 0.05 * max(h, w)
    paper_pixels = (lum > 0.7).astype(float)
    paper = np.ones_like(lum)
    for _ in range(3):  # normalised convolution: the paper level at every pixel from the bare paper around it
        paper = ndi.gaussian_filter(lum * paper_pixels, sigma) / np.maximum(ndi.gaussian_filter(paper_pixels, sigma), 1e-3)
        paper_pixels = (lum > 0.85 * paper).astype(float)
    return np.clip(1 - lum / np.clip(paper, 0.5, 1.0), 0, 1)


def ink_cut(rgb, gain=1.0, floor=0.04):
    """the drawing as the alpha channel over black, with the paper's noise floor taken off.
    gain strengthens a drawing that is drawn very faintly"""
    ink = np.clip(np.clip((how_much_ink(rgb) - floor) / (1 - floor), 0, 1) * gain, 0, 1)
    out = np.zeros(rgb.shape[:2] + (4,), np.uint8)
    out[..., 3] = np.round(ink * 255)
    return out


def photo_cut(rgb, bg, tolerance, band, neutral):
    from pymatting import estimate_alpha_cf, estimate_foreground_ml

    h, w, _ = rgb.shape
    # how much darker than the background, in the worst channel: a blue subject on white stays far from it
    away = np.clip((bg - rgb).max(axis=2) / max(bg.max(), 1e-3), 0, 1)
    looks_like_bg = away < tolerance
    if neutral:
        # a floor reflection or a grey shadow is colourless, and a coloured subject is not. so grey that is
        # connected to the edge goes too, which a plain distance from the background cannot say
        grey = (rgb.max(axis=2) - rgb.min(axis=2)) < 0.10
        looks_like_bg |= grey & (away < neutral)
    labels, count = ndi.label(looks_like_bg, GRID8)
    touching = np.unique(labels[border_ring(h, w, 2) & looks_like_bg])
    background = np.isin(labels, touching[touching > 0])
    # a big enclosed patch of background (the gap inside a handle) is background too, a pinprick highlight is not
    sizes = ndi.sum(looks_like_bg, labels, range(1, count + 1))
    for i in np.flatnonzero(sizes > 0.012 * h * w):
        background |= labels == i + 1

    # sure background, sure subject, and a band between them where the matting decides
    sure_bg = ndi.binary_erosion(background & (away < tolerance * 0.6), GRID8)
    sure_fg = ~ndi.binary_dilation(background, GRID8, iterations=band)
    trimap = np.full((h, w), 0.5)
    trimap[sure_bg], trimap[sure_fg] = 0.0, 1.0

    image = rgb.astype(np.float64)
    alpha = np.clip(estimate_alpha_cf(image, trimap), 0, 1)
    colour = np.clip(estimate_foreground_ml(image, alpha), 0, 1)  # the subject's colour with the background taken back out of the edge
    alpha[alpha < 0.02] = 0
    alpha[alpha > 0.985] = 1

    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = np.round(colour * 255)
    out[..., 3] = np.round(alpha * 255)
    return out


def rembg_cut(rgb):
    from rembg import new_session, remove

    session = new_session("u2net")
    result = remove(Image.fromarray(np.round(rgb * 255).astype(np.uint8)), session=session, alpha_matting=True,
                    alpha_matting_foreground_threshold=240, alpha_matting_background_threshold=10, alpha_matting_erode_size=8)
    return np.asarray(result.convert("RGBA"))


def drop_specks(rgba, smallest):
    """bits of dust and compression noise that float away from the subject"""
    labels, count = ndi.label(rgba[..., 3] > 25, GRID8)
    if not count:
        return rgba
    sizes = ndi.sum(np.ones_like(labels), labels, range(1, count + 1))
    gone = np.isin(labels, np.flatnonzero(sizes < smallest) + 1) & (rgba[..., 3] > 0)
    rgba = rgba.copy()
    rgba[gone] = 0
    return rgba


def crop(rgba, margin=0.02):
    ys, xs = np.where(rgba[..., 3] > 6)
    if not len(ys):
        sys.exit("nothing was left after the cut")
    pad = round(margin * max(xs.max() - xs.min(), ys.max() - ys.min()))
    h, w = rgba.shape[:2]
    y0, y1, x0, x1 = max(0, ys.min() - pad), min(h, ys.max() + pad + 1), max(0, xs.min() - pad), min(w, xs.max() + pad + 1)
    return rgba[y0:y1, x0:x1]


def run(name, src, args):
    rgb = np.asarray(Image.open(src).convert("RGB"), dtype=np.float64) / 255
    h, w, _ = rgb.shape
    bg, spread = estimate_background(rgb)
    away = np.clip((bg - rgb).max(axis=2) / max(bg.max(), 1e-3), 0, 1)
    subject = away > 0.15
    chroma = (rgb.max(axis=2) - rgb.min(axis=2))[subject]
    colourful = float(chroma.mean()) if chroma.size else 0.0

    engine = args.engine if args.engine != "auto" else ("matte" if spread < 0.05 else "rembg")
    mode = args.mode if args.mode != "auto" else ("ink" if colourful < 0.12 else "photo")
    band = args.band or max(3, round(0.008 * max(h, w)))

    if engine == "rembg":
        rgba, mode = rembg_cut(rgb), "photo"
    elif mode == "ink":
        rgba = ink_cut(rgb, args.gain)
    else:
        rgba = photo_cut(rgb, bg, args.tolerance, band, args.neutral)

    if not args.keep_specks:
        rgba = drop_specks(rgba, args.min_area)
    rgba = crop(rgba)
    if rgba.shape[1] > args.width:
        scale = args.width / rgba.shape[1]
        rgba = np.array(Image.fromarray(rgba).resize((args.width, round(rgba.shape[0] * scale)), Image.LANCZOS))

    out_dir = (args.out or ROOT / "assets" / "art")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.webp"
    # the colour under a fully clear pixel is never seen, so it is zeroed and costs nothing
    rgba[rgba[..., 3] == 0] = 0
    Image.fromarray(rgba).save(target, "WEBP", quality=args.quality, alpha_quality=100, method=6, exact=True)

    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest[name] = {"w": int(rgba.shape[1]), "h": int(rgba.shape[0]), "ink": mode == "ink"}
    manifest_path.write_text(json.dumps(dict(sorted(manifest.items())), indent=2) + "\n", encoding="utf-8")

    covered = float((rgba[..., 3] > 127).mean())
    print(f"{name}: {mode} cut by {engine}, background {np.round(bg * 255).astype(int).tolist()} (spread {spread:.3f}), "
          f"{src.stat().st_size // 1024} KB -> {rgba.shape[1]}x{rgba.shape[0]} webp {target.stat().st_size // 1024} KB, subject fills {covered:.0%}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="a picture, or name=picture to choose the output's name")
    ap.add_argument("--out", type=Path, help="default: assets/art")
    ap.add_argument("--mode", choices=["auto", "ink", "photo"], default="auto")
    ap.add_argument("--engine", choices=["auto", "matte", "rembg"], default="auto")
    ap.add_argument("--tolerance", type=float, default=0.08, help="photo: how far from the background colour still counts as background. raise it to drop a soft shadow")
    ap.add_argument("--neutral", type=float, default=0.0, help="photo: also count colourless grey as background up to this far from it (0.6 removes a floor reflection under a coloured subject)")
    ap.add_argument("--gain", type=float, default=1.0, help="ink: strengthen a faintly drawn picture, 2 doubles its darkness")
    ap.add_argument("--band", type=int, default=0, help="photo: pixels at the edge left for the matting to decide, 0 to size it to the picture")
    ap.add_argument("--min-area", type=int, default=40, help="pixels below which a loose speck is dropped")
    ap.add_argument("--keep-specks", action="store_true")
    ap.add_argument("--width", type=int, default=1400, help="widest the result may be")
    ap.add_argument("--quality", type=int, default=88)
    args = ap.parse_args()

    for item in args.inputs:
        name, _, path = item.partition("=") if "=" in item and not Path(item).exists() else (Path(item).stem, "", item)
        src = Path(path).expanduser()
        if not src.is_file():
            sys.exit(f"{src} is not a file")
        run(name, src, args)


if __name__ == "__main__":
    main()
