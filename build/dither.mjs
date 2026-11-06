// 1-bit image pipeline. Every picture on the site becomes a mask: ink pixels opaque, paper
// transparent. CSS paints the mask with the theme's ink colour, so one file works on cream paper
// by day and on black glass at night.
import sharp from 'sharp';

// grayscale 0..1 (0 = ink, 1 = paper) at the given width, contrast stretched
export async function loadGray(src, width, { gamma = 1, contrast = 1.15, flatten = '#ffffff', height } = {}) {
  const img = sharp(src).flatten({ background: flatten }).resize(width, height ?? null, { fit: height ? 'cover' : 'inside' })
    .greyscale().normalise();
  const { data, info } = await img.raw().toBuffer({ resolveWithObject: true });
  const out = new Float32Array(info.width * info.height);
  for (let i = 0; i < out.length; ++i) {
    let v = data[i * info.channels] / 255;
    v = Math.pow(v, gamma);
    v = (v - 0.5) * contrast + 0.5;
    out[i] = Math.min(1, Math.max(0, v));
  }
  return { gray: out, w: info.width, h: info.height };
}

// Atkinson: spreads 6/8 of the error, so highlights blow out and shadows stay rich, like an old Mac
export function atkinson({ gray, w, h }) {
  const g = Float32Array.from(gray), ink = new Uint8Array(w * h);
  const spread = [[1, 0], [2, 0], [-1, 1], [0, 1], [1, 1], [0, 2]];
  for (let y = 0; y < h; ++y)
    for (let x = 0; x < w; ++x) {
      const i = y * w + x, old = g[i], v = old < 0.5 ? 0 : 1;
      ink[i] = v === 0 ? 1 : 0;
      const err = (old - v) / 8;
      for (const [dx, dy] of spread) {
        const nx = x + dx, ny = y + dy;
        if (nx >= 0 && nx < w && ny < h) g[ny * w + nx] += err;
      }
    }
  return { ink, w, h };
}

// Floyd-Steinberg, serpentine: smoother midtones than Atkinson
export function floyd({ gray, w, h }) {
  const g = Float32Array.from(gray), ink = new Uint8Array(w * h);
  for (let y = 0; y < h; ++y) {
    const ltr = y % 2 === 0;
    for (let k = 0; k < w; ++k) {
      const x = ltr ? k : w - 1 - k, i = y * w + x, old = g[i], v = old < 0.5 ? 0 : 1, d = ltr ? 1 : -1;
      ink[i] = v === 0 ? 1 : 0;
      const err = old - v;
      if (x + d >= 0 && x + d < w) g[i + d] += err * 7 / 16;
      if (y + 1 < h) {
        if (x - d >= 0 && x - d < w) g[i + w - d] += err * 3 / 16;
        g[i + w] += err * 5 / 16;
        if (x + d >= 0 && x + d < w) g[i + w + d] += err * 1 / 16;
      }
    }
  }
  return { ink, w, h };
}

const BAYER8 = (() => {
  const m = [[0]];
  let b = m;
  for (let n = 1; n < 8; n *= 2) {
    const s = b.length, next = Array.from({ length: s * 2 }, () => new Array(s * 2));
    for (let y = 0; y < s; ++y) for (let x = 0; x < s; ++x) {
      const v = 4 * b[y][x];
      next[y][x] = v; next[y][x + s] = v + 2; next[y + s][x] = v + 3; next[y + s][x + s] = v + 1;
    }
    b = next;
  }
  return b.map((row) => row.map((v) => (v + 0.5) / 64));
})();

// ordered 8x8 Bayer: the crosshatch look of 1-bit game art
export function bayer({ gray, w, h }) {
  const ink = new Uint8Array(w * h);
  for (let y = 0; y < h; ++y) for (let x = 0; x < w; ++x) ink[y * w + x] = gray[y * w + x] < BAYER8[y & 7][x & 7] ? 1 : 0;
  return { ink, w, h };
}

// halftone: a dot per cell on a 45 degree screen, sized by how dark the cell is, drawn at scale
export function halftone({ gray, w, h }, { cell = 6, scale = 2 } = {}) {
  const W = w * scale, H = h * scale, ink = new Uint8Array(W * H);
  const c = Math.SQRT1_2;
  const sample = (x, y) => gray[Math.min(h - 1, Math.max(0, Math.floor(y))) * w + Math.min(w - 1, Math.max(0, Math.floor(x)))];
  for (let Y = 0; Y < H; ++Y) for (let X = 0; X < W; ++X) {
    // rotate into screen space, find the cell centre, rotate back to sample
    const u = (X * c + Y * c) / (cell * scale), v = (-X * c + Y * c) / (cell * scale);
    const cu = Math.floor(u) + 0.5, cv = Math.floor(v) + 0.5;
    const cx = (cu * c - cv * c) * cell * scale, cy = (cu * c + cv * c) * cell * scale;
    const darkness = 1 - sample(cx / scale, cy / scale);
    const r = Math.sqrt(darkness) * 0.72;
    const du = u - cu, dv = v - cv;
    ink[Y * W + X] = du * du + dv * dv < r * r ? 1 : 0;
  }
  return { ink, w: W, h: H };
}

// writes the mask: ink opaque white, paper fully transparent (CSS colours it)
export async function writeMask({ ink, w, h }, dest) {
  const rgba = Buffer.alloc(w * h * 4);
  for (let i = 0; i < w * h; ++i) {
    rgba[i * 4] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = 255;
    rgba[i * 4 + 3] = ink[i] ? 255 : 0;
  }
  await sharp(rgba, { raw: { width: w, height: h, channels: 4 } }).png({ compressionLevel: 9, palette: true, colours: 2 }).toFile(dest);
  return { w, h };
}

// a preview on paper, for looking at results while iterating
export async function writePreview({ ink, w, h }, dest, paper = [241, 236, 223], inkColour = [36, 44, 196]) {
  const rgb = Buffer.alloc(w * h * 3);
  for (let i = 0; i < w * h; ++i) {
    const c = ink[i] ? inkColour : paper;
    rgb[i * 3] = c[0]; rgb[i * 3 + 1] = c[1]; rgb[i * 3 + 2] = c[2];
  }
  await sharp(rgb, { raw: { width: w, height: h, channels: 3 } }).resize(w * 2, h * 2, { kernel: 'nearest' }).png().toFile(dest);
}
