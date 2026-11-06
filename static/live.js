// Live 1-bit art. Everything is drawn into a small pixel buffer (0 paper, 1 ink) with our own lines
// and fills, then shown scaled up with no smoothing, so it stays true 1-bit at any size.
// Colours come from the CSS palette of the window the canvas sits in.

const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

const BAYER = (() => {
  const b = [[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25], [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]];
  return b.map((r) => r.map((v) => (v + 0.5) / 64));
})();

function hexToRgb(c) {
  c = c.trim();
  if (c.startsWith('#')) {
    const n = parseInt(c.length === 4 ? c.slice(1).split('').map((x) => x + x).join('') : c.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const m = c.match(/\d+(\.\d+)?/g);
  return m ? m.slice(0, 3).map(Number) : [0, 0, 0];
}
const colours = (el) => {
  const s = getComputedStyle(el);
  return { ink: hexToRgb(s.getPropertyValue('--ink') || '#000'), paper: hexToRgb(s.getPropertyValue('--paper') || '#fff') };
};

// a 1-bit framebuffer the size of the canvas
function frame(canvas) {
  const w = canvas.width, h = canvas.height, ctx = canvas.getContext('2d'), img = ctx.createImageData(w, h);
  const buf = new Uint8Array(w * h);
  const fb = {
    w, h, buf,
    clear(v = 0) { buf.fill(v); },
    px(x, y, v = 1) { x |= 0; y |= 0; if (x >= 0 && y >= 0 && x < w && y < h) buf[y * w + x] = v; },
    line(x0, y0, x1, y1, v = 1) {
      x0 = Math.round(x0); y0 = Math.round(y0); x1 = Math.round(x1); y1 = Math.round(y1);
      const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
      let err = dx + dy;
      for (;;) {
        fb.px(x0, y0, v);
        if (x0 === x1 && y0 === y1) break;
        const e2 = 2 * err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
      }
    },
    // scanline fill; pattern(x, y) decides ink per pixel (solid, dither, stripes)
    poly(pts, pattern) {
      const ys = pts.map((p) => p[1]);
      const y0 = Math.max(0, Math.floor(Math.min(...ys))), y1 = Math.min(h - 1, Math.ceil(Math.max(...ys)));
      for (let y = y0; y <= y1; ++y) {
        const xs = [];
        for (let i = 0; i < pts.length; ++i) {
          const [ax, ay] = pts[i], [bx, by] = pts[(i + 1) % pts.length];
          if ((ay <= y + 0.5 && by > y + 0.5) || (by <= y + 0.5 && ay > y + 0.5)) xs.push(ax + (y + 0.5 - ay) / (by - ay) * (bx - ax));
        }
        xs.sort((a, b) => a - b);
        for (let k = 0; k + 1 < xs.length; k += 2)
          for (let x = Math.max(0, Math.round(xs[k])); x < Math.min(w, Math.round(xs[k + 1])); ++x) buf[y * w + x] = typeof pattern === 'function' ? pattern(x, y) : pattern;
      }
    },
    outline(pts, v = 1) { for (let i = 0; i < pts.length; ++i) fb.line(...pts[i], ...pts[(i + 1) % pts.length], v); },
    show(c) {
      const d = img.data;
      for (let i = 0; i < buf.length; ++i) {
        const col = buf[i] ? c.ink : c.paper;
        d[i * 4] = col[0]; d[i * 4 + 1] = col[1]; d[i * 4 + 2] = col[2]; d[i * 4 + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
    },
  };
  return fb;
}
const dither = (x, y, shade) => (shade < BAYER[y & 7][x & 7] ? 1 : 0);

// run fn(t) at most ~fps times a second while the canvas is on screen
function animate(canvas, fps, fn) {
  let visible = true, last = 0;
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(canvas);
  const loop = (now) => {
    requestAnimationFrame(loop);
    if (!visible || document.hidden || now - last < 1000 / fps) return;
    last = now;
    fn(now / 1000);
  };
  if (reduced) fn(0); else requestAnimationFrame(loop);
}

// ---------------------------------------------------------------- the moon
export function startMoon(canvas) {
  const fb = frame(canvas), { w, h } = fb, cx = w / 2, cy = h / 2, R = w * 0.42;
  let c = colours(canvas), light = [-0.55, -0.45, 0.7], target = light.slice();
  addEventListener('themechange', () => { c = colours(canvas); });
  // craters: centres on the unit sphere, radius, depth
  let s = 7;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const craters = Array.from({ length: 60 }, () => {
    const z = rnd() * 2 - 1, a = rnd() * Math.PI * 2, r = Math.sqrt(1 - z * z);
    return [Math.cos(a) * r, z, Math.sin(a) * r, 0.04 + rnd() * rnd() * 0.2];
  });
  const maria = Array.from({ length: 6 }, () => { const z = rnd() * 2 - 1, a = rnd() * 6.28, r = Math.sqrt(1 - z * z); return [Math.cos(a) * r, z, Math.sin(a) * r, 0.3 + rnd() * 0.3]; });
  canvas.addEventListener('pointermove', (e) => {
    const r = canvas.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width - 0.5) * 2, y = ((e.clientY - r.top) / r.height - 0.5) * 2;
    target = [-x, -y, 0.55];
  });
  canvas.addEventListener('pointerleave', () => { target = [-0.55, -0.45, 0.7]; });
  // a click spins it up; it eases back down
  let boost = 0, angle = 0, lastT = 0;
  canvas.addEventListener('click', () => { boost = Math.min(boost + 6, 18); });
  animate(canvas, 30, (t) => {
    light = light.map((v, i) => v + (target[i] - v) * 0.12);
    const ln = Math.hypot(...light), L = light.map((v) => v / ln);
    angle += (lastT ? t - lastT : 0) * (0.25 + boost); lastT = t; boost *= 0.94;
    const spin = angle, cs = Math.cos(spin), sn = Math.sin(spin);
    fb.clear(0);
    for (let y = 0; y < h; ++y) for (let x = 0; x < w; ++x) {
      const nx = (x + 0.5 - cx) / R, ny = (y + 0.5 - cy) / R, d2 = nx * nx + ny * ny;
      if (d2 > 1) continue;
      const nz = Math.sqrt(1 - d2);
      // the point on the turning sphere, for the surface texture
      const px = nx * cs + nz * sn, pz = -nx * sn + nz * cs, py = ny;
      let albedo = 0.95, tx = 0, ty = 0, tz = 0;
      for (const [mx, my, mz, mr] of maria) { const dd = Math.hypot(px - mx, py - my, pz - mz); if (dd < mr) albedo -= 0.3 * (1 - dd / mr); }
      for (const [kx, ky, kz, kr] of craters) {
        const ex = px - kx, ey = py - ky, ez = pz - kz, dd = Math.hypot(ex, ey, ez) / kr;
        if (dd >= 1.3) continue;
        // inside the bowl the normal leans toward the centre; on the rim it leans away
        const k = dd < 1 ? -1.6 * dd : 2.2 * (1.3 - dd);
        tx += ex / kr * k; ty += ey / kr * k; tz += ez / kr * k;
        if (dd < 0.35) albedo -= 0.08;
      }
      // tilt back from the turning sphere into screen space, then light it
      const sx = tx * cs - tz * sn, sz = tx * sn + tz * cs;
      let mxn = nx + sx * 0.5, myn = ny + ty * 0.5, mzn = nz + sz * 0.5;
      const ml = Math.hypot(mxn, myn, mzn); mxn /= ml; myn /= ml; mzn /= ml;
      const lambert = Math.max(0, mxn * L[0] + myn * L[1] + mzn * L[2]);
      const limb = Math.max(0, nx * L[0] + ny * L[1] + nz * L[2]);
      const shade = Math.min(1, Math.max(0, lambert * albedo * 1.2 * Math.min(1, limb * 4)));
      fb.px(x, y, dither(x, y, shade));
    }
    // a thin ring a little off the disc, like the print
    for (let a = 0; a < 6.283; a += 0.006) fb.px(cx + 6 + Math.cos(a) * (R + 4), cy - 5 + Math.sin(a) * (R + 4), 1);
    fb.show(c);
  });
}

// ---------------------------------------------------------------- the room
export function startRoom(canvas) {
  const fb = frame(canvas), { w, h } = fb;
  let c = colours(canvas);
  addEventListener('themechange', () => { c = colours(canvas); });
  const U = 8, OX = w / 2 - 8, OY = 78;
  // isometric: x runs down-right, y runs down-left, z is up
  const P = (x, y, z) => [OX + (x - y) * U, OY + (x + y) * U / 2 - z * U];
  const solid = 0;
  // a box with its three visible faces (top, +x side, +y side) filled with paper and outlined in ink
  const box = (x, y, z, dx, dy, dz, faces = {}) => {
    const top = [P(x, y, z + dz), P(x + dx, y, z + dz), P(x + dx, y + dy, z + dz), P(x, y + dy, z + dz)];
    const right = [P(x + dx, y, z), P(x + dx, y + dy, z), P(x + dx, y + dy, z + dz), P(x + dx, y, z + dz)];
    const left = [P(x, y + dy, z), P(x + dx, y + dy, z), P(x + dx, y + dy, z + dz), P(x, y + dy, z + dz)];
    fb.poly(top, faces.top ?? solid); fb.poly(right, faces.right ?? solid); fb.poly(left, faces.left ?? solid);
    fb.outline(top); fb.outline(right); fb.outline(left);
    return { top, right, left };
  };
  const stripes = (k) => (x, y) => (y % k === 0 ? 1 : 0);
  const shadeFace = (v) => (x, y) => dither(x, y, v);

  animate(canvas, 12, (t) => {
    fb.clear(0);
    // floor with boards, and the two back walls
    fb.poly([P(0, 0, 0), P(12, 0, 0), P(12, 10, 0), P(0, 10, 0)], (x, y) => 0);
    for (let k = 2; k < 12; k += 2) fb.line(...P(k, 0, 0), ...P(k, 10, 0));
    fb.outline([P(0, 0, 0), P(12, 0, 0), P(12, 10, 0), P(0, 10, 0)]);
    fb.outline([P(0, 0, 0), P(12, 0, 0), P(12, 0, 8), P(0, 0, 8)]);
    fb.outline([P(0, 0, 0), P(0, 10, 0), P(0, 10, 8), P(0, 0, 8)]);
    fb.line(...P(0, 0, 0), ...P(0, 0, 8));

    // window on the back wall: night outside, rain falling, blinds half down
    const win = [P(4, 0, 3.4), P(8.6, 0, 3.4), P(8.6, 0, 6.8), P(4, 0, 6.8)];
    fb.poly(win, 1);
    for (let k = 0; k < 26; ++k) {
      const rx = 4.2 + ((k * 0.37) % 4.2), phase = (t * 1.6 + k * 0.29) % 1, rz = 6.6 - phase * 3.2;
      const [sx, sy] = P(rx, 0, rz);
      fb.px(sx, sy, 0); fb.px(sx - 1, sy + 1, 0);
    }
    for (let z = 6.8; z > 5.6; z -= 0.25) fb.line(...P(4, 0, z), ...P(8.6, 0, z), 0);
    fb.outline(win); fb.line(...P(6.3, 0, 3.4), ...P(6.3, 0, 6.8));
    fb.outline([P(3.8, 0, 3.2), P(8.8, 0, 3.2), P(8.8, 0, 7), P(3.8, 0, 7)]);

    // shelf with books on the left wall, and a framed moon
    box(0, 2, 5.2, 0.9, 4, 0.25);
    for (let k = 0; k < 9; ++k) box(0.15, 2.3 + k * 0.4, 5.45, 0.55, 0.3, 0.7 + ((k * 7) % 3) * 0.2, { right: k % 3 === 0 ? 1 : 0 });
    const frameQ = [P(0, 6.8, 2.6), P(0, 9, 2.6), P(0, 9, 4.6), P(0, 6.8, 4.6)];
    fb.poly(frameQ, 0); fb.outline(frameQ);
    const [mx, my] = P(0, 7.9, 3.6);
    for (let a = 0; a < 6.3; a += 0.05) for (let r = 0; r < 5; ++r) if (Math.cos(a) * r > -1.5) fb.px(mx + Math.cos(a) * r, my + Math.sin(a) * r * 1.1, 1);

    // rug on the floor, dithered
    fb.poly([P(4, 4.2, 0), P(9.5, 4.2, 0), P(9.5, 8.5, 0), P(4, 8.5, 0)], (x, y) => dither(x, y, 0.75));
    fb.outline([P(4, 4.2, 0), P(9.5, 4.2, 0), P(9.5, 8.5, 0), P(4, 8.5, 0)]);

    // bed against the left wall: frame, mattress, blanket, pillow, someone asleep
    box(0, 5.4, 0, 3.6, 4.6, 1.0);
    box(0.1, 5.5, 1.0, 3.4, 4.4, 0.5);
    box(0.1, 7.2, 1.5, 3.4, 2.7, 0.35, { top: shadeFace(0.55) });
    box(0.25, 5.7, 1.5, 1.4, 1.4, 0.4);
    const [hx, hy] = P(1.0, 6.5, 2.35);
    for (let a = 0; a < 6.3; a += 0.15) fb.px(hx + Math.cos(a) * 3, hy + Math.sin(a) * 2.6, 1);
    for (let k = 0; k < 3; ++k) {
      const phase = (t * 0.45 + k / 3) % 1;
      const [zx, zy] = [hx + 6 + phase * 14, hy - 8 - phase * 26];
      const size = 2 + k;
      if (phase < 0.85) { fb.line(zx, zy, zx + size, zy); fb.line(zx + size, zy, zx, zy + size); fb.line(zx, zy + size, zx + size, zy + size); }
    }

    // desk against the back wall, a computer on it, code scrolling on the screen
    box(6.0, 0.2, 0, 4.6, 2.4, 2.6);
    box(6.4, 2.6, 0, 0.3, 0.1, 2.6);
    const screen = box(7.2, 0.4, 2.6, 2.4, 0.5, 2.0, { left: 1 });
    const [s0x, s0y] = P(7.4, 0.9, 4.35);
    for (let row = 0; row < 6; ++row) {
      const lineLen = 4 + ((row * 5 + Math.floor(t * 3)) * 7) % 11;
      const yy = Math.round(s0y + row * 2.6), xx = Math.round(s0x + row * 0);
      for (let k = 0; k < lineLen; ++k) fb.px(xx + k, yy + Math.round(k / 2), (k + row + Math.floor(t * 3)) % 5 ? 0 : 1);
    }
    if (Math.floor(t * 2) % 2) { const [cx2, cy2] = P(8.4, 0.9, 3.0); fb.px(cx2, cy2, 0); fb.px(cx2 + 1, cy2, 0); }
    box(7.4, 1.3, 2.6, 2.0, 0.8, 0.15, { top: stripes(2) });
    // a mug, steaming
    box(10.0, 1.0, 2.6, 0.45, 0.45, 0.55);
    const [mgx, mgy] = P(10.2, 1.2, 3.4);
    for (let k = 0; k < 6; ++k) fb.px(mgx + Math.round(Math.sin(t * 3 + k) * 1.2), mgy - k * 1.5, 1);

    // chair
    box(7.6, 3.6, 0, 1.6, 1.6, 1.4);
    box(7.6, 5.0, 1.4, 1.6, 0.3, 2.0);

    // a plant in the corner, swaying a little
    box(11.0, 0.4, 0, 0.8, 0.8, 1.0);
    const [bx, by] = P(11.4, 0.8, 1.0);
    for (let k = 0; k < 5; ++k) {
      const a = -1.2 + k * 0.6 + Math.sin(t * 1.3 + k) * 0.08, len = 12 + (k % 2) * 6;
      const ex = bx + Math.cos(a - 1.57) * len * 0.6, ey = by + Math.sin(a - 1.57) * len;
      fb.line(bx, by, ex, ey);
      fb.line(ex, ey, ex + (k % 2 ? 2 : -2), ey + 2);
    }
    fb.show(c);
  });
}

// ---------------------------------------------------------------- screensaver
const SAVER_PALETTES = [[[236, 227, 207], [13, 10, 6]], [[243, 201, 122], [13, 10, 6]], [[201, 185, 150], [13, 10, 6]], [[255, 244, 220], [20, 15, 10]], [[227, 181, 157], [13, 10, 6]]];
export function startSaver(el) {
  const canvas = el.querySelector('canvas');
  const LW = 190, LH = 44;
  let raf = 0, fb, stars, logo, pos, vel, pal = 0, flash = 0;
  const make = () => {
    canvas.width = Math.ceil(innerWidth / 3); canvas.height = Math.ceil(innerHeight / 3);
    fb = frame(canvas);
    stars = Array.from({ length: 220 }, (_, i) => Object.assign([Math.random() * 2 - 1, Math.random() * 2 - 1, Math.random()], { win: i % 9 === 0 }));
    const off = document.createElement('canvas'), o = off.getContext('2d');
    off.width = LW; off.height = LH;
    o.fillStyle = '#fff'; o.font = '44px VT323, monospace'; o.textBaseline = 'top'; o.fillText('PAWAN.SYS', 3, 2);
    const d = o.getImageData(0, 0, LW, LH).data;
    logo = [];
    for (let y = 0; y < LH; ++y) for (let x = 0; x < LW; ++x) if (d[(y * LW + x) * 4 + 3] > 120) logo.push([x, y]);
    pos = [Math.random() * (fb.w - LW), Math.random() * (fb.h - LH)]; vel = [0.8, 0.62];
  };
  const step = () => {
    raf = requestAnimationFrame(step);
    fb.clear(0);
    for (const st of stars) {
      st[2] -= 0.006;
      if (st[2] <= 0.02) { st[0] = Math.random() * 2 - 1; st[1] = Math.random() * 2 - 1; st[2] = 1; }
      const sx = fb.w / 2 + st[0] / st[2] * fb.w * 0.25, sy = fb.h / 2 + st[1] / st[2] * fb.h * 0.25;
      if (st.win) {
        const ww = Math.round(4 / st[2]), wh = Math.round(3 / st[2]);
        if (ww < 3) { fb.px(sx, sy, 1); continue; }
        fb.poly([[sx, sy], [sx + ww, sy], [sx + ww, sy + wh], [sx, sy + wh]], 0);
        fb.outline([[sx, sy], [sx + ww, sy], [sx + ww, sy + wh], [sx, sy + wh]]);
        fb.poly([[sx, sy], [sx + ww, sy], [sx + ww, sy + Math.max(1, wh / 5)], [sx, sy + Math.max(1, wh / 5)]], 1);
      } else {
        fb.px(sx, sy, 1);
        if (st[2] < 0.3) fb.px(sx + 1, sy, 1);
      }
    }
    pos[0] += vel[0]; pos[1] += vel[1];
    let hit = 0;
    if (pos[0] < 0 || pos[0] > fb.w - LW) { vel[0] *= -1; pos[0] = Math.max(0, Math.min(fb.w - LW, pos[0])); hit++; }
    if (pos[1] < 0 || pos[1] > fb.h - LH) { vel[1] *= -1; pos[1] = Math.max(0, Math.min(fb.h - LH, pos[1])); hit++; }
    if (hit) pal = (pal + 1) % SAVER_PALETTES.length;
    if (hit === 2) flash = 30;            // the corner. everyone waits for the corner.
    for (const [x, y] of logo) fb.px(pos[0] + x, pos[1] + y, 1);
    if (flash > 0) { flash--; for (let y = 0; y < fb.h; ++y) for (let x = 0; x < fb.w; ++x) if (dither(x, y, flash / 60)) fb.buf[y * fb.w + x] ^= 1; }
    fb.show({ ink: SAVER_PALETTES[pal][0], paper: SAVER_PALETTES[pal][1] });
  };
  const api = {
    visible: false,
    show() { if (api.visible) return; api.visible = true; el.hidden = false; make(); step(); },
    hide() { api.visible = false; el.hidden = true; cancelAnimationFrame(raf); },
  };
  el.addEventListener('pointerdown', () => api.hide());
  return api;
}

// ---------------------------------------------------------------- halftone cursor trail
export function startTrail(canvas) {
  const ctx = canvas.getContext('2d');
  const dots = [];
  let ink = getComputedStyle(document.body).color;
  addEventListener('themechange', () => { ink = getComputedStyle(document.body).color; });
  const size = () => { canvas.width = innerWidth; canvas.height = innerHeight; };
  size();
  addEventListener('resize', size);
  addEventListener('pointermove', (e) => {
    // snap to a 6px screen so the trail reads as halftone, not a blur
    dots.push({ x: Math.round(e.clientX / 6) * 6, y: Math.round(e.clientY / 6) * 6, life: 1 });
    if (dots.length > 60) dots.shift();
  }, { passive: true });
  const loop = () => {
    requestAnimationFrame(loop);
    if (!dots.length) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = ink;
    for (const d of dots) {
      d.life -= 0.045;
      if (d.life <= 0) continue;
      ctx.beginPath();
      ctx.arc(d.x, d.y, 2.6 * d.life, 0, Math.PI * 2);
      ctx.fill();
    }
    while (dots.length && dots[0].life <= 0) dots.shift();
    if (!dots.length) ctx.clearRect(0, 0, canvas.width, canvas.height);
  };
  loop();
}
