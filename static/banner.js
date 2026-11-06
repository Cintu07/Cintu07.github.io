// The intro banner: a late-summer evening from a 90s anime, drawn in vector at the screen's full
// resolution (sharp at 4k), cel-shaded in the site's beige. A tall cloud, power lines, a train,
// birds, film grain, and the intro as fansub subtitles. At night: a dark brown sky, stars, lit windows.

const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const LINES = ["i'm pawan.", 'i build database and inference stuff,', 'and break it a lot.', 'this is where i write down why.', 'every number in a post came from a program that ran.'];

const DAY = {
  sky: ['#f7ecd6', '#f1dcb6', '#e6c28d'], glow: 'rgba(255, 238, 200, .9)',
  cloud: ['#d2b78c', '#eddcbb', '#fbf4e4'], far: '#cbb089', mid: '#a48a64', ink: '#231d14', lit: '#f6e7c4',
  wire: '#231d14', grain: .07, stars: false,
};
const NIGHT = {
  sky: ['#100c08', '#1e170f', '#35281a'], glow: 'rgba(243, 201, 122, .22)',
  cloud: ['#2a2016', '#3a2d1f', '#4d3d29'], far: '#2a2016', mid: '#1a140d', ink: '#070504', lit: '#f3c97a',
  wire: '#070504', grain: .09, stars: true,
};

function seeded(seed) { let s = seed; return () => ((s = (s * 16807) % 2147483647) / 2147483647); }

export function startBanner(canvas, subtitle) {
  const ctx = canvas.getContext('2d');
  const rnd = seeded(1996);
  // the cloud is a cluster of circles, a tower that spreads at the top like an anvil
  const puffs = [];
  for (let i = 0; i < 70; ++i) {
    const t = i / 70;
    const spread = 0.04 + t * t * 0.13;
    puffs.push({ x: 0.62 + (rnd() - 0.5) * spread * 2, y: 0.78 - t * 0.66 + rnd() * 0.05, r: 0.065 + rnd() * 0.06 + (1 - t) * 0.045, w: rnd() * 6.28 });
  }
  const wisps = Array.from({ length: 5 }, (_, i) => ({ x: rnd(), y: 0.12 + rnd() * 0.25, len: 0.12 + rnd() * 0.2, speed: 0.004 + rnd() * 0.006 }));
  const stars = Array.from({ length: 140 }, () => [rnd(), rnd() * 0.6, rnd()]);
  const city = [];
  for (let x = 0, k = 0; x < 1.05; ++k) { const w = 0.015 + rnd() * 0.04; city.push([x, w, 0.04 + rnd() * 0.12, rnd()]); x += w + rnd() * 0.004; }
  const near = [];
  for (let x = 0; x < 1.05;) { const w = 0.03 + rnd() * 0.06; near.push([x, w, 0.03 + rnd() * 0.08, rnd()]); x += w; }
  const birds = Array.from({ length: 7 }, (_, i) => [i * 0.025 + rnd() * 0.02, rnd() * 0.05, rnd() * 6]);
  // film grain, made once and slid around every frame
  const grain = document.createElement('canvas');
  grain.width = grain.height = 160;
  const g = grain.getContext('2d'), gi = g.createImageData(160, 160);
  for (let i = 0; i < gi.data.length; i += 4) { const v = rnd() * 255; gi.data[i] = gi.data[i + 1] = gi.data[i + 2] = v; gi.data[i + 3] = 255; }
  g.putImageData(gi, 0, 0);

  let W = 0, H = 0, dpr = 1, theme = DAY;
  const pickTheme = () => { theme = document.documentElement.dataset.theme === 'night' ? NIGHT : DAY; };
  pickTheme();
  addEventListener('themechange', pickTheme);
  const size = () => {
    dpr = Math.min(innerWidth < 720 ? 2 : 3, devicePixelRatio || 1);
    // layout size, not the on-screen rect: the window may still be mid zoom-in when this runs
    W = canvas.width = Math.round(canvas.clientWidth * dpr);
    H = canvas.height = Math.round(canvas.clientHeight * dpr);
  };
  new ResizeObserver(size).observe(canvas);
  size();

  const X = (x) => x * W, Y = (y) => y * H;
  function cloudLayer(t, colour, dx, dy, shrink) {
    ctx.fillStyle = colour;
    ctx.beginPath();
    for (const p of puffs) {
      const r = (p.r - shrink) * (1 + Math.sin(t * 0.4 + p.w) * 0.03);
      if (r <= 0) continue;
      const cx = X(p.x + dx + t * 0.0015 % 1), cy = Y(p.y + dy);
      ctx.moveTo(cx + r * H, cy);
      ctx.arc(cx, cy, r * H, 0, Math.PI * 2);
    }
    ctx.fill();
  }

  // one utility pole with crossarms; returns where its wires attach
  function pole(x, top) {
    ctx.fillStyle = theme.ink;
    const px = X(x), w = Math.max(3, W * 0.006);
    ctx.fillRect(px - w / 2, Y(top), w, H - Y(top));
    const arms = [];
    for (let k = 0; k < 2; ++k) {
      const ay = Y(top + 0.04 + k * 0.07), aw = W * (0.05 - k * 0.012);
      ctx.fillRect(px - aw, ay, aw * 2, Math.max(2, H * 0.008));
      for (const s of [-1, -0.45, 0.45, 1]) {
        const ix = px + s * aw * 0.92;
        ctx.fillRect(ix - w * 0.35, ay - H * 0.018, w * 0.7, H * 0.018);
        arms.push([ix, ay - H * 0.018]);
      }
    }
    return arms;
  }

  function frame(t) {
    const th = theme;
    // sky
    const sky = ctx.createLinearGradient(0, 0, 0, H);
    sky.addColorStop(0, th.sky[0]); sky.addColorStop(0.55, th.sky[1]); sky.addColorStop(1, th.sky[2]);
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, W, H);
    const glow = ctx.createRadialGradient(X(0.82), Y(0.82), 0, X(0.82), Y(0.82), W * 0.45);
    glow.addColorStop(0, th.glow); glow.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, W, H);
    if (th.stars) {
      for (const [sx, sy, tw] of stars) {
        ctx.globalAlpha = 0.4 + 0.6 * Math.abs(Math.sin(t * 0.8 + tw * 9));
        ctx.fillStyle = '#efe2c4';
        ctx.fillRect(X(sx), Y(sy), dpr * 1.4, dpr * 1.4);
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = '#f2ecd8';
      ctx.beginPath(); ctx.arc(X(0.16), Y(0.22), H * 0.07, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = th.sky[0];
      ctx.beginPath(); ctx.arc(X(0.16) + H * 0.03, Y(0.22) - H * 0.015, H * 0.065, 0, Math.PI * 2); ctx.fill();
    }
    // far city, then the near rooftops with lit windows
    ctx.fillStyle = th.far;
    for (const [x, w, h] of city) ctx.fillRect(X(x), Y(0.84 - h), X(w) + 1, Y(h) + Y(0.2));
    // the elevated track, and a train crossing every fourteen seconds
    const trackY = 0.8;
    ctx.fillStyle = th.mid;
    ctx.fillRect(0, Y(trackY), W, H * 0.018);
    for (let x = 0.03; x < 1; x += 0.09) ctx.fillRect(X(x), Y(trackY), W * 0.008, H);
    const phase = (t % 14) / 14;
    if (phase < 0.6) {
      const tx = -0.5 + phase / 0.6 * 1.8;
      for (let car = 0; car < 4; ++car) {
        const cx = X(tx + car * 0.125), cw = X(0.12), cy = Y(trackY - 0.075);
        ctx.fillStyle = th.ink;
        ctx.fillRect(cx, cy, cw, Y(0.072));
        ctx.fillStyle = th.lit;
        for (let w = 0; w < 5; ++w) ctx.fillRect(cx + cw * (0.08 + w * 0.18), cy + Y(0.016), cw * 0.11, Y(0.022));
      }
    }
    ctx.fillStyle = th.ink;
    for (const [x, w, h, lit] of near) {
      ctx.fillRect(X(x), Y(0.93 - h), X(w) + 1, H);
      if (th.stars && lit > 0.4) {
        ctx.fillStyle = th.lit;
        for (let k = 0; k < 3; ++k) if ((lit * 10 + k) % 2 > 0.8) ctx.fillRect(X(x + w * (0.2 + k * 0.25)), Y(0.95 - h), X(w * 0.12), Y(0.012));
        ctx.fillStyle = th.ink;
      }
    }
    // birds, a small flock going home
    const bx = ((t * 0.035) % 1.4) - 0.2;
    ctx.strokeStyle = th.ink;
    ctx.lineWidth = Math.max(1.2, dpr * 1.3);
    for (const [ox, oy, f] of birds) {
      const x = X(bx + ox), y = Y(0.3 + oy + Math.sin(t + f) * 0.008), s = H * 0.014, flap = Math.sin(t * 9 + f) * s * 0.6;
      ctx.beginPath(); ctx.moveTo(x - s, y - flap); ctx.lineTo(x, y); ctx.lineTo(x + s, y - flap); ctx.stroke();
    }
    // poles in the foreground, wires sagging between them and off the edges
    const a = pole(0.1, 0.12), b = pole(0.9, 0.2);
    ctx.strokeStyle = th.wire;
    ctx.lineWidth = Math.max(1, dpr * 1.2);
    const sway = Math.sin(t * 0.7) * H * 0.006;
    a.forEach((p, i) => {
      const q = b[i];
      ctx.beginPath();
      ctx.moveTo(-10, p[1] + H * 0.05);
      ctx.quadraticCurveTo((p[0] - 10) / 2, p[1] + H * 0.09 + sway, p[0], p[1]);
      ctx.quadraticCurveTo((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + H * 0.16 + sway, q[0], q[1]);
      ctx.quadraticCurveTo((q[0] + W) / 2, q[1] + H * 0.08 + sway, W + 10, q[1] + H * 0.03);
      ctx.stroke();
    });
    // grain and a soft vignette, like film run through a cheap scanner
    ctx.globalAlpha = th.grain;
    ctx.globalCompositeOperation = 'overlay';
    const ox = Math.floor(rnd() * 160), oy = Math.floor(rnd() * 160);
    ctx.fillStyle = ctx.createPattern(grain, 'repeat');
    ctx.save(); ctx.translate(-ox, -oy); ctx.scale(dpr, dpr); ctx.fillRect(0, 0, W / dpr + 160, H / dpr + 160); ctx.restore();
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = 1;
    const vig = ctx.createRadialGradient(W / 2, H / 2, H * 0.4, W / 2, H / 2, W * 0.65);
    vig.addColorStop(0, 'rgba(0,0,0,0)'); vig.addColorStop(1, th.stars ? 'rgba(0,0,0,.45)' : 'rgba(60,40,10,.22)');
    ctx.fillStyle = vig;
    ctx.fillRect(0, 0, W, H);
  }

  // subtitles: typed in, held, then the next line
  let line = 0, shownAt = 0;
  function subtitles(t) {
    if (!subtitle) return;
    const text = LINES[line], age = t - shownAt, chars = Math.min(text.length, Math.floor(age * 28));
    subtitle.textContent = reduced ? LINES.slice(0, 4).join(' ') : text.slice(0, chars);
    if (age > text.length / 28 + 2.2) { line = (line + 1) % LINES.length; shownAt = t; }
  }

  let visible = true, last = 0;
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(canvas);
  const loop = (now) => {
    requestAnimationFrame(loop);
    if (!visible || document.hidden || now - last < 33) return;
    last = now;
    const t = now / 1000;
    frame(t);
    subtitles(t);
  };
  if (reduced) { frame(4); subtitles(0); } else requestAnimationFrame(loop);
}
