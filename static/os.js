// PAWAN.SYS desktop: windows, taskbar, start menu, day/night, music, boot, screensaver, cursor trail.
// Everything here is optional: with scripts off the pages are plain readable documents.
import { startMoon, startRoom, startSaver, startTrail } from './live.js';
import { startBanner } from './banner.js';

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const root = document.documentElement;
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  once: (k) => { try { if (sessionStorage.getItem(k)) return false; sessionStorage.setItem(k, '1'); return true; } catch { return false; } },
};

// ---------------------------------------------------------------- clock
const clock = $('.clock');
const tick = () => {
  const d = new Date();
  clock.textContent = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' });
  clock.dateTime = d.toISOString();
};
tick();
setInterval(tick, 1000);

// ---------------------------------------------------------------- day / night
function toggleTheme() {
  const next = root.dataset.theme === 'night' ? 'day' : 'night';
  root.dataset.theme = next;
  store.set('pawan-theme', next);
  $('#theme-color')?.setAttribute('content', next === 'night' ? '#14100b' : '#ece6d6');
  window.dispatchEvent(new Event('themechange'));
}
$('.tray-theme').addEventListener('click', toggleTheme);

// ---------------------------------------------------------------- music
const audio = $('#music'), musicButton = $('.tray-music');
function toggleMusic() {
  if (!audio) return;
  if (audio.paused) audio.play().catch(() => {}); else audio.pause();
}
audio?.addEventListener('play', () => musicButton.setAttribute('aria-pressed', 'true'));
audio?.addEventListener('pause', () => musicButton.setAttribute('aria-pressed', 'false'));
musicButton?.addEventListener('click', toggleMusic);

// ---------------------------------------------------------------- start menu
const start = $('.start'), menu = $('.startmenu');
function setMenu(open) { menu.hidden = !open; start.setAttribute('aria-expanded', String(open)); if (open) $('a, button', menu)?.focus(); }
start.addEventListener('click', (e) => { e.stopPropagation(); setMenu(menu.hidden); });
document.addEventListener('click', (e) => { if (!menu.hidden && !menu.contains(e.target)) setMenu(false); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setMenu(false); });

// actions shared by the start menu and desktop icons
const actions = {
  theme: toggleTheme,
  music: toggleMusic,
  saver: () => saver.show(),
  bin: () => openBin(),
};
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (el && actions[el.dataset.action]) { e.preventDefault(); setMenu(false); actions[el.dataset.action](); }
});

// ---------------------------------------------------------------- windows
let topZ = 10;
function focus(win) {
  $$('.win.focused').forEach((w) => w.classList.remove('focused'));
  win.classList.add('focused');
  win.style.zIndex = String(++topZ);
  $$('.task').forEach((t) => t.classList.toggle('on', t.dataset.win === win.id && !win.classList.contains('min')));
}
for (const win of $$('.desktop .win')) {
  win.addEventListener('pointerdown', () => focus(win));
  $('.min', win)?.addEventListener('click', () => { win.classList.toggle('min'); focus(win); });
  $('.max', win)?.addEventListener('click', () => { win.classList.toggle('maxed'); focus(win); });
  $('.close', win)?.addEventListener('click', () => trash(win));
  // drag by the title bar on wide screens; the window keeps its place in the layout, offset by a transform
  const bar = $('.bar', win);
  let drag = null;
  bar.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button') || innerWidth < 1100 || win.classList.contains('maxed')) return;
    const [x, y] = (win.dataset.offset ?? '0,0').split(',').map(Number);
    drag = { sx: e.clientX, sy: e.clientY, x, y };
    bar.setPointerCapture(e.pointerId);
    win.classList.add('dragging');
  });
  bar.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const x = drag.x + e.clientX - drag.sx, y = drag.y + e.clientY - drag.sy;
    win.style.transform = `translate(${x}px, ${y}px)`;
    win.dataset.offset = `${x},${y}`;
  });
  const end = () => { drag = null; win.classList.remove('dragging'); };
  bar.addEventListener('pointerup', end);
  bar.addEventListener('pointercancel', end);
  bar.addEventListener('dblclick', (e) => { if (!e.target.closest('button')) win.classList.toggle('min'); });
}
for (const task of $$('.task')) {
  task.addEventListener('click', () => {
    const win = document.getElementById(task.dataset.win);
    if (!win) return;
    if (win.classList.contains('closed') || win.classList.contains('min')) { win.classList.remove('closed', 'min'); focus(win); }
    else if (win.classList.contains('focused')) { win.classList.add('min'); task.classList.remove('on'); return; }
    else focus(win);
    win.scrollIntoView({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' });
  });
}

// ---------------------------------------------------------------- rubber-band selection on the empty desk
{
  let lasso = null, sx = 0, sy = 0;
  const pickable = () => $('.ico, .card');
  document.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.pointerType === 'touch') return;
    if (e.target.closest('.win, .card, .ico, a, button, .taskbar, .startmenu, input') || !e.target.closest('.desktop')) return;
    sx = e.clientX; sy = e.clientY;
    lasso = document.createElement('div');
    lasso.className = 'lasso';
    document.body.append(lasso);
    pickable().forEach((el) => el.classList.remove('picked'));
  });
  addEventListener('pointermove', (e) => {
    if (!lasso) return;
    const x = Math.min(sx, e.clientX), y = Math.min(sy, e.clientY), w = Math.abs(e.clientX - sx), h = Math.abs(e.clientY - sy);
    Object.assign(lasso.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' });
    for (const el of pickable()) {
      const r = el.getBoundingClientRect();
      el.classList.toggle('picked', r.left < x + w && r.right > x && r.top < y + h && r.bottom > y);
    }
  });
  addEventListener('pointerup', () => { lasso?.remove(); lasso = null; });
}

// ---------------------------------------------------------------- recycle bin
const binned = [];
const binIcon = () => $$('.bin-ico').find((el) => el.offsetParent !== null);
function trash(win) {
  const from = win.getBoundingClientRect(), icon = binIcon();
  win.classList.remove('maxed');
  if (icon && !reduced) {
    // a dashed outline of the window shrinks into the bin, the way windows used to minimise
    const to = icon.getBoundingClientRect();
    const ghost = document.createElement('div');
    ghost.className = 'flying';
    Object.assign(ghost.style, { left: from.left + 'px', top: from.top + 'px', width: from.width + 'px', height: from.height + 'px' });
    document.body.append(ghost);
    ghost.animate([
      { transform: 'none', opacity: 1 },
      { transform: `translate(${to.left + to.width / 2 - from.left - from.width / 2}px, ${to.top + to.height / 2 - from.top - from.height / 2}px) scale(.04)`, opacity: 0.6 },
    ], { duration: 460, easing: 'steps(7)' }).finished.then(() => {
      ghost.remove();
      icon.classList.remove('gulp'); void icon.offsetWidth; icon.classList.add('gulp');
    });
  }
  win.classList.add('closed');
  $$(`.task[data-win="${win.id}"]`).forEach((t) => t.classList.remove('on'));
  if (!binned.includes(win)) binned.push(win);
  renderBin();
}
function restore(win) {
  win.classList.remove('closed', 'min');
  binned.splice(binned.indexOf(win), 1);
  focus(win);
  renderBin();
}
function renderBin() {
  $$('.bin-ico').forEach((el) => el.classList.toggle('full', binned.length > 0));
  for (const list of $$('.binitems')) {
    list.replaceChildren(...binned.map((w) => {
      const li = document.createElement('li');
      li.innerHTML = `<span>${w.dataset.title}</span><button type="button">Restore</button>`;
      li.querySelector('button').addEventListener('click', () => restore(w));
      return li;
    }));
  }
  $$('.bincount').forEach((el) => { el.textContent = `${binned.length} object(s)`; });
}
// the bin window: the one on the home page, or a pop-up anywhere else
function openBin() {
  let bin = $('#bin');
  if (!bin) {
    bin = document.createElement('section');
    bin.className = 'win pal-paper binpop';
    bin.id = 'bin';
    bin.dataset.title = 'Recycle Bin';
    bin.innerHTML = `<header class="bar"><span class="title">Recycle Bin</span><span class="ctl"><button class="close" type="button" aria-label="close">×</button></span></header>
<div class="body"><div class="binlist"><p class="head"><span>Name</span><span>Original Location</span></p><ul class="binitems"></ul><p class="empty">nothing in here.</p></div><p class="binbtns"><button class="btn restore-all" type="button">Restore all</button></p></div>
<footer class="status"><span class="bincount">0 object(s)</span><span>this page</span></footer>`;
    document.body.append(bin);
    $('.close', bin).addEventListener('click', () => bin.remove());
    $('.restore-all', bin).addEventListener('click', () => [...binned].forEach(restore));
    renderBin();
    return;
  }
  if (binned.includes(bin)) restore(bin);
  bin.classList.remove('closed', 'min');
  focus(bin);
  bin.scrollIntoView({ block: 'center', behavior: reduced ? 'auto' : 'smooth' });
}
$$('.restore-all').forEach((b) => b.addEventListener('click', () => [...binned].forEach(restore)));

// ---------------------------------------------------------------- the 404: the error follows you, leaving copies behind
if (document.body.classList.contains('oops')) {
  const where = $('.where');
  if (where) where.textContent = location.pathname;
  const random = $('.random');
  if (random) {
    const posts = random.dataset.posts.split(' ');
    random.href = posts[Math.floor(Math.random() * posts.length)];
  }
  const error = $('#error');
  let lastStamp = 0;
  const ghosts = [];
  if (error && !reduced) addEventListener('pointermove', (e) => {
    if (e.target.closest('#error') || performance.now() - lastStamp < 28) return;
    lastStamp = performance.now();
    const ghost = error.cloneNode(true);
    ghost.removeAttribute('id');
    ghost.classList.add('ghost');
    ghost.setAttribute('aria-hidden', 'true');
    const r = error.getBoundingClientRect();
    Object.assign(ghost.style, { left: e.clientX - r.width / 2 + 'px', top: e.clientY - 15 + 'px', width: r.width + 'px', animation: 'none' });
    document.body.append(ghost);
    ghosts.push(ghost);
    if (ghosts.length > 70) ghosts.shift().remove();
  });
}

// ---------------------------------------------------------------- window menus that do things
document.addEventListener('click', async (e) => {
  const item = e.target.closest('[data-menu]');
  if (!item) return;
  const what = item.dataset.menu, win = item.closest('.win');
  if (what === 'theme') return toggleTheme();
  if (what === 'restore-all') return [...binned].forEach(restore);
  if (what === 'copy-link') {
    try { await navigator.clipboard.writeText(location.href.split('#')[0]); item.lastChild.textContent = 'opy link ✓'; }
    catch { item.lastChild.textContent = 'opy link ✗'; }
    setTimeout(() => { item.lastChild.textContent = 'opy link'; }, 1500);
    return;
  }
  if (what.startsWith('sort-')) {
    const grid = $('.cards', win), cards = $$('.card', grid);
    const key = {
      'sort-new': (a, b) => b.dataset.date.localeCompare(a.dataset.date),
      'sort-old': (a, b) => a.dataset.date.localeCompare(b.dataset.date),
      'sort-short': (a, b) => a.dataset.minutes - b.dataset.minutes,
      'sort-random': () => Math.random() - 0.5,
    }[what];
    // cards shuffle with a quick stepped fade so the change is visible
    grid.animate([{ opacity: 1 }, { opacity: 0.2 }, { opacity: 1 }], { duration: 260, easing: 'steps(3)' });
    grid.append(...cards.sort(key));
    $$('[data-menu^="sort-"]', win).forEach((b) => b.classList.toggle('on', b === item));
  }
});

// ---------------------------------------------------------------- big books: lean toward the mouse, open on click
for (const book of $$('.book3d.big')) {
  const stage = book.closest('.stage') ?? book;
  stage.addEventListener('pointermove', (e) => {
    if (book.classList.contains('open')) return;
    const r = stage.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
    book.style.setProperty('--ry', `${-24 + x * 40}deg`);
    book.style.setProperty('--rx', `${6 - y * 18}deg`);
  });
  stage.addEventListener('pointerleave', () => { book.style.removeProperty('--ry'); book.style.removeProperty('--rx'); });
  book.addEventListener('click', () => {
    // first click opens the cover; a click on the open book reads it
    if (book.classList.contains('open') && book.dataset.pdf) { location.href = book.dataset.pdf; return; }
    book.classList.add('open');
    const caption = stage.querySelector('.caption');
    if (caption) caption.textContent = book.dataset.pdf ? 'click again to read the pdf' : 'opened';
  });
}

// ---------------------------------------------------------------- code blocks: copy
document.addEventListener('click', async (e) => {
  const button = e.target.closest('figure.code .copy');
  if (!button) return;
  const text = $('code', button.closest('figure')).innerText;
  try { await navigator.clipboard.writeText(text); button.textContent = 'copied'; }
  catch { button.textContent = 'select it'; }
  setTimeout(() => { button.textContent = 'copy'; }, 1400);
});

// ---------------------------------------------------------------- reading progress and contents
const prose = $('.prose'), progress = $('.progress'), tocLinks = $$('.w-toc a');
if (prose) {
  const heads = $$('h2[id]', prose);
  const onScroll = () => {
    const r = prose.getBoundingClientRect();
    const done = Math.min(1, Math.max(0, (innerHeight * 0.4 - r.top) / r.height));
    if (progress) progress.textContent = `${Math.round(done * 100)}%`;
    let current = heads[0]?.id;
    for (const h of heads) if (h.getBoundingClientRect().top < innerHeight * 0.3) current = h.id;
    tocLinks.forEach((a) => a.classList.toggle('here', a.getAttribute('href') === `#${current}`));
  };
  addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

// ---------------------------------------------------------------- live art
$$('canvas.moon').forEach((c) => startMoon(c));
$$('canvas.anime').forEach((c) => startBanner(c, c.parentElement.querySelector('.sub')));
$$('canvas.room').forEach((c) => startRoom(c));
if (!reduced && matchMedia('(pointer: fine)').matches) startTrail($('.trail'));

// ---------------------------------------------------------------- screensaver after a minute and a half idle
const saver = startSaver($('.saver'));
let idle;
const wake = () => { clearTimeout(idle); if (saver.visible) saver.hide(); idle = setTimeout(() => !reduced && saver.show(), 90_000); };
['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll'].forEach((ev) => addEventListener(ev, wake, { passive: true }));
wake();

// ---------------------------------------------------------------- boot, once per visit, home only
if (document.body.classList.contains('home') && !reduced && store.once('pawan-booted')) {
  const boot = document.createElement('div');
  boot.className = 'boot';
  boot.setAttribute('aria-hidden', 'true');
  const lines = [
    'PAWAN BIOS v26.11  (C) 2026 cintu07',
    '',
    'CPU   : snapdragon x / i7-13650hx ........ OK',
    'MEMORY: 16384K ........................... OK',
    'GPU   : adreno 630 (emulated in numpy) ... OK',
    'LOAD  : writing.dat  papers.dat  moon.1bit',
    '',
    'starting PAWAN.SYS',
  ];
  const pre = document.createElement('pre');
  boot.append(pre);
  document.body.append(boot);
  let i = 0;
  const finish = () => { boot.classList.add('done'); setTimeout(() => boot.remove(), 400); removeEventListener('keydown', finish); };
  boot.addEventListener('pointerdown', finish);
  addEventListener('keydown', finish);
  const step = () => {
    if (i >= lines.length) { pre.innerHTML += '<span class="cursor">█</span>'; setTimeout(finish, 450); return; }
    pre.textContent += lines[i++] + '\n';
    setTimeout(step, i === 1 ? 260 : 120);
  };
  step();
}
