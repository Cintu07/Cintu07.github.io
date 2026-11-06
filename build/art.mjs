// Generated art: a small signed-distance raymarcher that renders one grayscale scene per post,
// which dither.mjs then turns into a 1-bit mask. Every scene is a picture of the post's idea.
// Scenes are deterministic: same slug, same picture.

// ---------------------------------------------------------------- vectors
const v = (x, y, z) => [x, y, z];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const len = (a) => Math.hypot(a[0], a[1], a[2]);
const norm = (a) => mul(a, 1 / (len(a) || 1));
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const mix = (a, b, t) => a + (b - a) * t;

// ---------------------------------------------------------------- distance functions
const sphere = (p, r) => len(p) - r;
const box = (p, b, r = 0) => {
  const q = [Math.abs(p[0]) - b[0] + r, Math.abs(p[1]) - b[1] + r, Math.abs(p[2]) - b[2] + r];
  return Math.hypot(Math.max(q[0], 0), Math.max(q[1], 0), Math.max(q[2], 0)) + Math.min(Math.max(q[0], q[1], q[2]), 0) - r;
};
const cylinder = (p, r, h) => { // axis y
  const d0 = Math.hypot(p[0], p[2]) - r, d1 = Math.abs(p[1]) - h;
  return Math.min(Math.max(d0, d1), 0) + Math.hypot(Math.max(d0, 0), Math.max(d1, 0));
};
const capsule = (p, a, b, r) => {
  const pa = sub(p, a), ba = sub(b, a), h = clamp(dot(pa, ba) / dot(ba, ba), 0, 1);
  return len(sub(pa, mul(ba, h))) - r;
};
const torus = (p, R, r) => Math.hypot(Math.hypot(p[0], p[2]) - R, p[1]) - r;
const smin = (a, b, k) => { const h = clamp(0.5 + 0.5 * (b - a) / k, 0, 1); return mix(b, a, h) - k * h * (1 - h); };

// seeded random and value noise, for craters, terrain and grain
export function rng(seed) {
  let s = 0;
  for (const c of String(seed)) s = (s * 31 + c.charCodeAt(0)) >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}
const hash3 = (x, y, z) => { const n = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453; return n - Math.floor(n); };
function noise3(p) {
  const i = p.map(Math.floor), f = p.map((x, k) => x - i[k]), u = f.map((t) => t * t * (3 - 2 * t));
  let r = 0;
  for (let dz = 0; dz < 2; ++dz) for (let dy = 0; dy < 2; ++dy) for (let dx = 0; dx < 2; ++dx) {
    const w = (dx ? u[0] : 1 - u[0]) * (dy ? u[1] : 1 - u[1]) * (dz ? u[2] : 1 - u[2]);
    r += w * hash3(i[0] + dx, i[1] + dy, i[2] + dz);
  }
  return r;
}
const fbm = (p, o = 4) => { let a = 0.5, s = 0; for (let k = 0; k < o; ++k) { s += a * noise3(p); p = mul(p, 2.03); a *= 0.5; } return s; };

// ---------------------------------------------------------------- renderer
// scene.sdf(p) -> distance; scene.camera {from, to, fov}; scene.light (direction); scene.sky (0..1)
export function render(scene, w, h) {
  const { from, to, fov = 0.9 } = scene.camera;
  const fwd = norm(sub(to, from)), right = norm(cross(fwd, [0, 1, 0])), up = cross(right, fwd);
  const light = norm(scene.light ?? [0.6, 0.8, -0.4]);
  const sky = scene.sky ?? 1, maxT = scene.far ?? 40, eps = 0.0015;
  const sdf = scene.sdf;
  const normal = (p) => {
    const e = 0.0015;
    return norm([
      sdf([p[0] + e, p[1], p[2]]) - sdf([p[0] - e, p[1], p[2]]),
      sdf([p[0], p[1] + e, p[2]]) - sdf([p[0], p[1] - e, p[2]]),
      sdf([p[0], p[1], p[2] + e]) - sdf([p[0], p[1], p[2] - e]),
    ]);
  };
  const shadow = (p, n) => {
    let res = 1, t = 0.02;
    for (let i = 0; i < 40 && t < 12; ++i) {
      const d = sdf(add(add(p, mul(n, 0.004)), mul(light, t)));
      if (d < 0.0008) return 0;
      res = Math.min(res, 9 * d / t);
      t += clamp(d, 0.02, 0.5);
    }
    return clamp(res, 0, 1);
  };
  const occlusion = (p, n) => {
    let o = 0, s = 1;
    for (let i = 1; i <= 5; ++i) { const hh = 0.03 * i * i; o += (hh - sdf(add(p, mul(n, hh)))) * s; s *= 0.7; }
    return clamp(1 - 2.2 * o, 0, 1);
  };
  const out = new Float32Array(w * h);
  const aspect = w / h;
  for (let y = 0; y < h; ++y) for (let x = 0; x < w; ++x) {
    const u = ((x + 0.5) / w * 2 - 1) * aspect * fov, vv = (1 - (y + 0.5) / h * 2) * fov;
    const dir = norm(add(add(fwd, mul(right, u)), mul(up, vv)));
    let t = 0, hit = false, p = from;
    for (let i = 0; i < 160; ++i) {
      p = add(from, mul(dir, t));
      const d = sdf(p);
      if (d < eps * (1 + t)) { hit = true; break; }
      t += d * 0.85;
      if (t > maxT) break;
    }
    let shade;
    if (!hit) shade = typeof sky === 'function' ? sky(dir) : sky;
    else {
      const n = normal(p);
      const diffuse = Math.max(0, dot(n, light)) * shadow(p, n);
      const rim = Math.pow(1 - Math.max(0, -dot(n, dir)), 3);
      shade = 0.06 + 0.86 * diffuse + 0.12 * rim;
      shade *= mix(0.55, 1, occlusion(p, n));
      // the floor is paper; only the shadows on it are drawn
      if (scene.floor !== undefined && p[1] < scene.floor + 0.012 * (1 + t)) { const sh = shadow(p, n); shade = sh > 0.9 ? 1 : mix(0.3, 1, sh); }
      if (scene.surface) shade = scene.surface(p, n, shade);
      const fog = scene.fog ? 1 - Math.exp(-scene.fog * t) : 0;
      shade = mix(shade, typeof sky === 'function' ? sky(dir) : sky, fog);
    }
    out[y * w + x] = clamp(shade, 0, 1);
  }
  return out;
}

// ---------------------------------------------------------------- scenes, one per post

const SCENES = {
  // the adreno die as a city of ALU blocks running to the horizon
  'a630-emulator': () => {
    const r = rng('a630');
    const heights = Array.from({ length: 4096 }, () => { const x = r(); return x < 0.1 ? 0.55 + r() * 0.7 : x < 0.35 ? 0.22 + r() * 0.2 : 0.06 + r() * 0.08; });
    return {
      camera: { from: [-5.5, 2.6, -7], to: [1.2, 0.1, 2.5], fov: 0.5 },
      light: [0.45, 0.8, -0.35], sky: 1, fog: 0.045,
      sdf: (p) => {
        const s = 0.6;
        const cx = Math.round(p[0] / s) * s, cz = Math.round(p[2] / s) * s;
        const hh = heights[((Math.round(cx / s) + 64) * 64 + Math.round(cz / s) + 64) & 4095];
        const block = box(sub(p, [cx, hh, cz]), [0.22, hh, 0.22], 0.02);
        // traces between the blocks, cut into the die
        const trace = Math.abs(((p[0] / s + 0.5) % 1 + 1) % 1 - 0.5) < 0.06 || Math.abs(((p[2] / s + 0.5) % 1 + 1) % 1 - 0.5) < 0.06;
        return Math.min(block, p[1] + (trace ? 0.03 : 0));
      },
    };
  },
  // the same discs summed in a different order: a field of stacks whose tops never quite agree
  'batch-invariance': () => {
    const r = rng('order');
    const parts = [0.08, 0.1, 0.12, 0.14, 0.16];
    const tops = Array.from({ length: 1024 }, () => parts.reduce((a, b) => a + b, 0) + (r() - 0.5) * 0.12);
    const order = Array.from({ length: 1024 }, () => [...parts].sort(() => r() - 0.5));
    return {
      camera: { from: [-4.8, 1.9, -6.2], to: [1.5, 0.35, 3], fov: 0.5 },
      light: [-0.5, 0.75, -0.45], sky: 1, fog: 0.05,
      sdf: (p) => {
        const s = 0.9;
        const ix = Math.round(p[0] / s), iz = Math.round(p[2] / s);
        const k = ((ix + 32) * 32 + iz + 32) & 1023;
        const q = sub(p, [ix * s, 0, iz * s]);
        let d = p[1], y = 0;
        const scale = tops[k] / 0.6;
        order[k].forEach((h, i) => {
          const hh = h * scale;
          d = Math.min(d, cylinder(sub(q, [0, y + hh / 2, 0]), 0.34 - i * 0.035, hh / 2 - 0.01) - 0.006);
          y += hh;
        });
        return d;
      },
    };
  },
  // a ternary field, -1 0 +1, rippling as it is reordered (kept: it fits the post)
  'ciot-t2p-kernel': () => {
    const r = rng('t2p');
    const vals = Array.from({ length: 4096 }, () => Math.floor(r() * 3) - 1);
    return {
      camera: { from: [-6, 4.2, -7.5], to: [1, -0.4, 2], fov: 0.5 },
      light: [0.3, 0.9, -0.5], sky: 1, fog: 0.05,
      sdf: (p) => {
        const cx = Math.round(p[0] / 0.5) * 0.5, cz = Math.round(p[2] / 0.5) * 0.5;
        const idx = ((Math.round(cx / 0.5) + 64) * 64 + Math.round(cz / 0.5) + 64) & 4095;
        const wave = Math.sin(cx * 0.9 + cz * 0.35) * 0.5 + 0.5;
        const hh = vals[idx] * 0.2 * wave;
        const tile = box(sub(p, [cx, hh, cz]), [0.2, 0.08, 0.2], 0.03);
        return Math.min(tile, p[1] + 0.35);
      },
    };
  },
  // 64 weights in 16 bytes: ternary tiles packed four to a byte, seen from above
  'ciot-ternary-inference': () => {
    const r = rng('pack');
    const vals = Array.from({ length: 4096 }, () => Math.floor(r() * 3) - 1);
    return {
      camera: { from: [-2.5, 6.2, -6.5], to: [1.2, -0.3, 1.5], fov: 0.52 },
      light: [-0.4, 0.9, -0.35], sky: 1, fog: 0.04,
      sdf: (p) => {
        // four tiles to a pack, a wider gap between packs
        const pack = 1.9, cell = 0.42;
        const px = Math.floor(p[0] / pack), local = p[0] - px * pack;
        const ix = clamp(Math.floor(local / cell), 0, 3);
        const cx = px * pack + (ix + 0.5) * cell + 0.07;
        const cz = Math.round(p[2] / 0.5) * 0.5;
        const v = vals[((px + 64) * 4 + ix) * 64 % 4096 + ((Math.round(cz / 0.5) + 64) & 63) & 4095];
        const tile = v === 0 ? box(sub(p, [cx, -0.02, cz]), [0.16, 0.03, 0.2], 0.01) : box(sub(p, [cx, v * 0.14, cz]), [0.16, 0.1, 0.2], 0.03);
        const tray = box(sub(p, [px * pack + 0.91, -0.14, cz]), [0.9, 0.04, 0.24], 0.02);
        return Math.min(tile, tray, p[1] + 0.3);
      },
    };
  },
  // a loss landscape running to the horizon, contour lines, and the ball's dotted path down it
  'gradient-descent': () => {
    const surface = (x, z) => 0.55 * Math.sin(x * 0.7) * Math.cos(z * 0.55) + 0.25 * Math.sin(x * 1.7 + z * 1.1) * 0.5 + 0.012 * ((x - 1) ** 2 + (z - 3) ** 2) - 0.5;
    const path = [];
    let x = -2.6, z = -1.2;
    for (let i = 0; i < 46; ++i) {
      const e = 0.01, gx = (surface(x + e, z) - surface(x - e, z)) / (2 * e), gz = (surface(x, z + e) - surface(x, z - e)) / (2 * e);
      path.push([x, surface(x, z) + 0.06, z]);
      x -= 0.35 * gx; z -= 0.35 * gz;
    }
    const ball = path[path.length - 1];
    return {
      camera: { from: [-4.2, 1.6, -4.6], to: [1.5, -0.5, 3.5], fov: 0.52 },
      light: [0.5, 0.75, -0.4], sky: 1, fog: 0.05, far: 30,
      sdf: (p) => {
        let d = (p[1] - surface(p[0], p[2])) * 0.55;
        for (let i = 0; i < path.length - 1; i += 2) d = Math.min(d, sphere(sub(p, path[i]), 0.05));
        return Math.min(d, sphere(sub(p, [ball[0], ball[1] + 0.13, ball[2]]), 0.2));
      },
      surface: (p, n, s) => {
        if (p[1] > surface(p[0], p[2]) + 0.03) return s;
        const h = surface(p[0], p[2]);
        return Math.abs(((h * 9) % 1 + 1) % 1 - 0.5) < 0.06 ? 0.04 : 0.3 + 0.7 * s;
      },
    };
  },
  // rows of memory cells, dotted arrows arcing from pointers to what they point at
  'pointers': () => {
    const arcs = [[0, 2, 0, 9], [0, 5, 1, 1], [1, 7, 2, 3], [2, 1, 0, 12], [1, 11, 2, 15], [2, 8, 1, 17], [0, 14, 2, 20]];
    const cell = (row, i) => [row * 1.1 - 1.1, 0.62, i * 0.95];
    const dots = [];
    for (const [ra, ia, rb, ib] of arcs) {
      const a = cell(ra, ia), b = cell(rb, ib), lift = 0.5 + Math.abs(ib - ia) * 0.12;
      for (let k = 0; k <= 14; ++k) {
        const t = k / 14;
        dots.push([[mix(a[0], b[0], t), a[1] + 0.05 + Math.sin(Math.PI * t) * lift, mix(a[2], b[2], t)], k === 14 ? 0.1 : 0.055]);
      }
    }
    return {
      camera: { from: [-0.2, 2.1, -2.4], to: [0, 0.4, 7], fov: 0.55 },
      light: [0.55, 0.8, -0.4], sky: 1, fog: 0.05, floor: 0,
      sdf: (p) => {
        const row = clamp(Math.round((p[0] + 1.1) / 1.1), 0, 2), i = clamp(Math.round(p[2] / 0.95), 0, 24);
        let d = Math.min(box(sub(p, [row * 1.1 - 1.1, 0.3, i * 0.95]), [0.42, 0.3, 0.4], 0.04), p[1]);
        if (p[1] > 0.55) for (const [c, rr] of dots) d = Math.min(d, sphere(sub(p, c), rr));
        return d;
      },
    };
  },
  // a membership lattice: every node joined to its neighbours, the doubtful ones hollow
  'styx-membership-system': () => {
    const r = rng('styx');
    const doubt = Array.from({ length: 1024 }, () => r() < 0.28);
    return {
      camera: { from: [-3.6, 2.6, -4.6], to: [1, 0.4, 3], fov: 0.5 },
      light: [0.4, 0.85, -0.5], sky: 1, fog: 0.055, floor: -0.45,
      sdf: (p) => {
        const s = 1.25;
        const ix = Math.round(p[0] / s), iz = Math.round(p[2] / s);
        const c = [ix * s, 0.3, iz * s];
        const q = sub(p, c);
        const ball = sphere(q, 0.26);
        const node = doubt[((ix + 32) * 32 + iz + 32) & 1023] ? Math.max(ball, -sphere(sub(q, [0, 0.05, -0.12]), 0.21)) : ball;
        const rodX = Math.hypot(q[1], q[2]) - 0.035, rodZ = Math.hypot(q[1], q[0]) - 0.035;
        return Math.min(node, rodX, rodZ, p[1] + 0.45);
      },
    };
  },
  // every layer charges you something: a tunnel of layers, one small cube of real work at the end
  'the-interface-tax': () => ({
    camera: { from: [0.45, 0.3, -1.2], to: [0, -0.05, 8], fov: 0.62 },
    light: [-0.35, 0.5, -0.8], sky: 1, fog: 0.035,
    sdf: (p) => {
      const k = Math.max(0, Math.round(p[2] / 1.1));
      const q = [p[0], p[1], p[2] - k * 1.1];
      const outer = box(q, [2.2, 1.35, 0.06], 0.01), inner = box(q, [1.75, 1.0, 0.2], 0.01);
      const frame = Math.max(outer, -inner);
      const work = box(sub(p, [0, -0.15, 14]), [0.22, 0.22, 0.22], 0.02);
      return Math.min(frame, work, p[1] + 1.36);
    },
  }),
  // the card is still on file: rows of cards, one slot empty, its ghost coming apart into dots
  'your-ai-has-amnesia': () => ({
    camera: { from: [-2.2, 1.25, -1.9], to: [0.4, 0.4, 4], fov: 0.55 },
    light: [-0.45, 0.8, -0.55], sky: 1, fog: 0.06, floor: 0,
    sdf: (p) => {
      const row = clamp(Math.round(p[0] / 1.2), -2, 2), i = clamp(Math.round(p[2] / 0.55), 0, 30);
      const c = [row * 1.2, 0.36, i * 0.55];
      let d = Math.min(p[1], box(sub(p, [row * 1.2, 0.03, i * 0.55]), [0.55, 0.03, 0.24], 0.01));
      if (row === 0 && i === 2) {
        const q = sub(p, c), b = q.map((x) => Math.round(x / 0.08) * 0.08);
        const inside = Math.abs(b[0]) <= 0.44 && Math.abs(b[1]) <= 0.28 && Math.abs(b[2]) < 0.01;
        const keep = hash3(b[0] * 9, b[1] * 9, 3) > 0.62 - b[1] * 0.5;
        return inside && keep ? Math.min(d, sphere(sub(q, b), 0.022)) : Math.min(d, Math.max(box(q, [0.5, 0.34, 0.06]), 0.02));
      }
      return Math.min(d, box(sub(p, c), [0.46, 0.3, 0.03], 0.03));
    },
  }),
};

// the first compiler: an expression graph, ops joined to their inputs, leaves at the bottom
SCENES['book-the-first-compiler'] = () => {
  const nodes = [], links = [];
  const levels = [[0], [-1.1, 1.1], [-1.7, -0.55, 0.55, 1.7], [-2.1, -1.4, -0.7, 0, 0.7, 1.4, 2.1]];
  levels.forEach((xs, l) => xs.forEach((x, i) => {
    const p = [x, 2.6 - l * 0.95, l === 3 ? 0.2 : 0];
    nodes.push([p, l === 3]);
    if (l > 0) {
      const parents = levels[l - 1];
      const j = Math.min(parents.length - 1, Math.floor(i * parents.length / xs.length));
      links.push([[parents[j], 2.6 - (l - 1) * 0.95, 0], p]);
    }
  }));
  return {
    camera: { from: [0.6, 1.9, -6.4], to: [0, 1.3, 0], fov: 0.5 },
    light: [-0.5, 0.8, -0.6], sky: 1, floor: -0.6,
    sdf: (p) => {
      let d = p[1] + 0.6;
      for (const [c, leaf] of nodes) d = Math.min(d, leaf ? box(sub(p, c), [0.2, 0.2, 0.2], 0.04) : sphere(sub(p, c), 0.27));
      for (const [a, b] of links) d = Math.min(d, capsule(p, a, b, 0.045));
      return d;
    },
  };
};
// below the code: a chip package with its pins, sitting on a board
SCENES['book-below-the-code'] = () => ({
  camera: { from: [2.6, 3.4, -3.4], to: [0, 0, 0], fov: 0.55 },
  light: [-0.4, 0.85, -0.4], sky: 1, floor: 0,
  sdf: (p) => {
    const body = box(sub(p, [0, 0.28, 0]), [1.15, 0.16, 1.15], 0.04);
    const dot = sphere(sub(p, [-0.8, 0.46, -0.8]), 0.08);
    // pins along all four sides
    const along = (u) => clamp(Math.round(u / 0.2) * 0.2, -1.0, 1.0);
    const pinX = box(sub(p, [along(p[0]), 0.12, Math.sign(p[2]) * 1.32]), [0.05, 0.03, 0.2], 0.01);
    const pinZ = box(sub(p, [Math.sign(p[0]) * 1.32, 0.12, along(p[2])]), [0.2, 0.03, 0.05], 0.01);
    return Math.min(Math.max(body, -dot), pinX, pinZ, p[1]);
  },
  surface: (p, n, s) => (p[1] < 0.03 && Math.abs(((p[0] * 2.5) % 1 + 1) % 1 - 0.5) < 0.04 && Math.abs(p[2]) > 1.6 ? 0.1 : s),
});

// the site's own picture: a CRT computer on a desk, a window open on its screen, keyboard, floppies, a mug
SCENES.hero = () => {
  const SCREEN_Z = -0.66;
  return {
    camera: { from: [-2.35, 1.95, -3.75], to: [0.1, 0.72, -0.35], fov: 0.47 },
    light: [-0.55, 0.85, -0.5], sky: 1, floor: 0,
    sdf: (p) => {
      // monitor: a deep rounded case, a recessed bulging screen, a neck and a foot
      const caseBox = box(sub(p, [0, 1.12, 0.12]), [0.86, 0.72, 0.78], 0.14);
      const recess = box(sub(p, [0, 1.16, SCREEN_Z - 0.12]), [0.64, 0.5, 0.2], 0.06);
      const screen = Math.max(sphere(sub(p, [0, 1.16, 2.6]), 3.3), box(sub(p, [0, 1.16, SCREEN_Z]), [0.64, 0.5, 0.3]));
      const monitor = Math.min(Math.max(caseBox, -recess), screen);
      const neck = cylinder(sub(p, [0, 0.3, 0.15]), 0.22, 0.12);
      const foot = box(sub(p, [0, 0.07, 0.12]), [0.6, 0.07, 0.5], 0.05);
      // keyboard in front, keys as a grid of little bumps
      const kb = box(sub(p, [0.05, 0.08, -1.45]), [0.95, 0.07, 0.33], 0.04);
      const kx = clamp(Math.round((p[0] - 0.05) / 0.16) * 0.16 + 0.05, -0.83, 0.93), kz = clamp(Math.round((p[2] + 1.45) / 0.15) * 0.15 - 1.45, -1.7, -1.2);
      const key = box(sub(p, [kx, 0.17, kz]), [0.06, 0.03, 0.055], 0.015);
      // three floppies, stacked a little crooked, and a mug
      let floppies = 10;
      for (let k = 0; k < 3; ++k) {
        const a = 0.25 * k - 0.2, c = Math.cos(a), s = Math.sin(a);
        const q = sub(p, [1.55, 0.03 + k * 0.05, -0.9]);
        floppies = Math.min(floppies, box([q[0] * c - q[2] * s, q[1], q[0] * s + q[2] * c], [0.3, 0.02, 0.3], 0.01));
      }
      const mugBody = Math.max(cylinder(sub(p, [-1.45, 0.27, -0.95]), 0.2, 0.27) - 0.01, -cylinder(sub(p, [-1.45, 0.4, -0.95]), 0.16, 0.25));
      const handle = torus([p[0] + 1.66, p[2] + 0.95, p[1] - 0.28].map((v, i) => v), 0.11, 0.03);
      return Math.min(monitor, neck, foot, kb, key, floppies, mugBody, handle, p[1]);
    },
    surface: (p, n, s) => {
      // the screen glows: a light window with a dark title bar, scanlines over all of it
      if (p[2] < SCREEN_Z + 0.02 && Math.abs(p[0]) < 0.62 && Math.abs(p[1] - 1.16) < 0.48) {
        const u = p[0], v = p[1] - 1.16;
        let g = 0.12;
        if (u > -0.45 && u < 0.38 && v > -0.3 && v < 0.3) g = v > 0.2 ? 0.05 : 0.92;          // window and its title bar
        if (u > -0.38 && u < 0.2 && v < 0.12 && v > -0.24 && Math.abs(((v * 18) % 1 + 1) % 1 - 0.5) < 0.16) g = 0.2; // text lines
        if (((p[1] * 60) % 1 + 1) % 1 < 0.28) g *= 0.75;                                       // scanlines
        return g;
      }
      // the floppies: a metal shutter and a label on top
      if (p[0] > 1.2 && p[0] < 1.9 && p[1] > 0.1 && p[1] < 0.18 && n[1] > 0.8) {
        const q = [p[0] - 1.55, p[2] + 0.9];
        if (Math.abs(q[0]) < 0.12 && q[1] > 0.12) return 0.15;
        if (Math.abs(q[0]) < 0.2 && q[1] < -0.02 && q[1] > -0.24) return 0.95;
      }
      return s;
    },
  };
};

// a moon for anything without its own scene
SCENES.default = (slug) => {
  const r = rng(slug), lx = r() - 0.5;
  return {
    camera: { from: [0, 0, -4], to: [0, 0, 0], fov: 0.42 },
    light: [lx * 2, 0.3, -0.5], sky: 0.97,
    sdf: (p) => sphere(p, 1.25) - 0.06 * fbm(mul(p, 2.6)),
  };
};

export const hasScene = (slug) => slug in SCENES;
export function sceneFor(slug) { return (SCENES[slug] ?? SCENES.default)(slug); }
