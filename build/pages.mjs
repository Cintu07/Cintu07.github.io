// Page templates. Every page is a desktop: a marquee at the top, windows in the middle, a taskbar
// at the bottom. Windows take a palette (paper and ink pair); masks and text follow it.

export const SITE = 'https://cintu07.github.io';
const NAME = 'pawan';
const TAGLINE = "i'm pawan. i build database and inference stuff and break it a lot. this is where i write down why.";

export const PALETTES = ['paper', 'lilac', 'night', 'moss', 'clay', 'blueprint'];
const FIXED = {
  'a630-emulator': 'night', 'batch-invariance': 'lilac', 'ciot-t2p-kernel': 'paper', 'ciot-ternary-inference': 'moss',
  'gradient-descent': 'clay', 'pointers': 'blueprint', 'styx-membership-system': 'lilac', 'the-interface-tax': 'paper',
  'your-ai-has-amnesia': 'night',
};
export function paletteFor(slug) {
  return 'paper';
  let h = 0;
  for (const c of slug) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return PALETTES[h % PALETTES.length];
}

const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const pretty = (d) => `${String(d.getUTCDate()).padStart(2, '0')} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
const caps = (d) => pretty(d).toUpperCase();

// ---------------------------------------------------------------- pixel icons
// '#' ink, '+' fill, '.' empty. Drawn as rects so they stay crisp at any size.
const ICON_GRIDS = {
  writing: ['..############..', '..#..#..#..#.#..', '.##############.', '.#++++++++++++#.', '.#+##########+#.', '.#++++++++++++#.', '.#+#########++#.', '.#++++++++++++#.', '.#+##########+#.', '.#++++++++++++#.', '.#+#######++++#.', '.#++++++++++++#.', '.##############.'],
  papers: ['##############..', '#..#########.#..', '#..#########..#.', '#..#########...#', '#..#########...#', '#..............#', '#++++++++++++++#', '#+############+#', '#+#..........#+#', '#+#.########.#+#', '#+#..........#+#', '#+#.######...#+#', '#+############+#', '################'],
  books: ['...##########...', '..#++++++++++#..', '.##########++#..', '.#.........#+#..', '.#..######.#+#..', '.#.........#+#..', '.#..####...#+#..', '.#.........#+#..', '.#.........#+#..', '.#.........#+#..', '.#.........#+#..', '.#.........##...', '.###########....'],
  music: ['.....######.....', '...##++++++##...', '..#++++++++++#..', '.#++++####++++#.', '.#+++#....#+++#.', '#+++#..##..#+++#', '#+++#.#..#.#+++#', '#+++#.#..#.#+++#', '#+++#..##..#+++#', '.#+++#....#+++#.', '.#++++####++++#.', '..#++++++++++#..', '...##++++++##...', '.....######.....'],
  seams: ['.##############.', '.#............#.', '.#.##########.#.', '.#.#++++++++#.#.', '.#.#++#++#++#.#.', '.#.#++++++++#.#.', '.#.#++####++#.#.', '.#.#++++++++#.#.', '.#.##########.#.', '.#............#.', '.##############.', '......####......', '....########....'],
  eye: ['.##########.....', '.#++++++++##....', '.#++++++++#.#...', '.#++++++++####..', '.#+++####++++#..', '.#++#....#+++#..', '.#+#..##..#++#..', '.#+#..##..#++#..', '.#++#....#+++#..', '.#+++####++++#..', '.#+++++++++++#..', '.#############..'],
  web: ['.....######.....', '...##..#...##...', '..#...#.#....#..', '.#####...######.', '.#...#...#....#.', '#.....#.#......#', '################', '#.....#.#......#', '.#...#...#....#.', '.#####...######.', '..#...#.#....#..', '...##..#...##...', '.....######.....'],
  terminal: ['################', '#++++++++++++++#', '################', '#..............#', '#.##...........#', '#..##..........#', '#...##.........#', '#..##..........#', '#.##..#####....#', '#..............#', '################'],
  binFull: ['..#...##..#.....', '.#+#.#++#.#+#...', '..#+##++##+#....', '.##############.', '..############..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..############..'],
  bin: ['....########....', '.##############.', '..############..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..#..#..#..#.#..', '..############..'],
  moon: ['.....######.....', '...##++++++##...', '..#+++++++++.#..', '.#++++++++++..#.', '.#+++++++++...#.', '#++++++++++....#', '#+++++++++.....#', '#+++++++++.....#', '#++++++++++....#', '.#+++++++++...#.', '.#++++++++++..#.', '..#+++++++++.#..', '...##++++++##...', '.....######.....'],
};
export function icon(name, scale = 3) {
  const rows = ICON_GRIDS[name];
  const w = Math.max(...rows.map((r) => r.length)), h = rows.length;
  let rects = '';
  rows.forEach((row, y) => [...row].forEach((c, x) => {
    if (c === '#') rects += `<rect x="${x}" y="${y}" width="1" height="1"/>`;
    else if (c === '+') rects += `<rect class="f" x="${x}" y="${y}" width="1" height="1"/>`;
  }));
  return `<svg class="px" viewBox="0 0 ${w} ${h}" width="${w * scale}" height="${h * scale}" shape-rendering="crispEdges" aria-hidden="true">${rects}</svg>`;
}

// ---------------------------------------------------------------- pieces

const mask = (art, cls = '', label = '') => art
  ? `<div class="mask ${cls}" style="--src:url(${art.src});aspect-ratio:${art.w}/${art.h}"${label ? ` role="img" aria-label="${esc(label)}"` : ' aria-hidden="true"'}></div>`
  : '';

// a window; drag by the title bar on wide screens, buttons minimise and close
export function win({ id, title, body, menu, status, cls = '', glyph = '', label }) {
  const palette = 'paper';
  const menuHtml = menu ? `<nav class="menu" aria-label="${esc(title)} menu">${menu.map(([t, href, action]) => href ? `<a href="${href}"${/^https?:/.test(href) ? ' rel="me"' : ''}><u>${t[0]}</u>${t.slice(1)}</a>` : `<button type="button" data-menu="${action}"><u>${t[0]}</u>${t.slice(1)}</button>`).join('')}</nav>` : '';
  const statusHtml = status ? `<footer class="status">${status.map((s) => `<span>${s}</span>`).join('')}</footer>` : '';
  return `<section class="win pal-${palette} ${cls}" id="${id}" data-title="${esc(title)}" aria-label="${esc(label ?? title)}">
<header class="bar"><span class="title">${glyph}${esc(title)}</span><span class="ctl"><button class="min" type="button" aria-label="minimise">_</button><button class="max" type="button" aria-label="maximise">□</button><button class="close" type="button" aria-label="close">×</button></span></header>
${menuHtml}<div class="body">${body}</div>${statusHtml}
</section>`;
}

const tagPills = (tags) => tags.slice(0, 3).map((t) => `<span class="pill">${esc(t)}</span>`).join('');
const titleWithUnderline = (title) => {
  const words = esc(title).split(' ');
  const last = words.pop();
  return `${words.join(' ')} <u>${last}</u>`;
};

function card(p, i) {
  return `<article class="card pal-${p.palette}" data-date="${p.iso}" data-minutes="${p.minutes}">
<a class="cardlink" href="${p.url}" aria-label="${esc(p.title)}"></a>
<div class="kicker">${tagPills(p.tags)}<span class="no">№${String(i + 1).padStart(2, '0')}</span></div>
<h3>${titleWithUnderline(p.title)}</h3>
${mask(p.art, 'art')}
<p class="meta">DATE: ${caps(p.date)}. TAGS: ${esc(p.tags.join(', ').toUpperCase())}. ${p.minutes} MIN READ.</p>
<p class="desc">${esc(p.description)}</p>
<div class="go"><span>READ</span><span class="arrow">⟶</span></div>
</article>`;
}

// ---------------------------------------------------------------- layout

const MARQUEE = '▷ i know the bugs will be found. ◆ i build database and inference stuff and break it a lot. ◆ this is where i write down why. ◆ every number here was printed by a program that ran. (￣┰￣*) ◆ ';

export function page({ title, description, path, body, nav = '', ctx, og = '/assets/og/home.png', bodyClass = '' }) {
  const full = path === '/' ? NAME : `${title} · ${NAME}`;
  const latest = ctx.posts[0];
  const tasks = (ctx.tasks ?? []).map(([id, t, g]) => `<button class="task" type="button" data-win="${id}">${icon(g, 1)}<span>${esc(t)}</span></button>`).join('');
  return `<!doctype html>
<html lang="en" data-theme="day">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>${esc(full)}</title>
<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${SITE}${path}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:image" content="${SITE}${og}">
<meta property="og:url" content="${SITE}${path}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#ece6d6" id="theme-color">
<link rel="alternate" type="application/atom+xml" href="/feed.xml" title="pawan">
<link rel="icon" href="/static/icon.svg" type="image/svg+xml">
<link rel="preload" href="/assets/fonts/dotgothic16.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/zilla-slab-600.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/static/site.css">
<script>(function(){try{var t=localStorage.getItem('pawan-theme');if(t)document.documentElement.dataset.theme=t;else if(matchMedia('(prefers-color-scheme: dark)').matches)document.documentElement.dataset.theme='night';}catch(e){}})();</script>
</head>
<body class="${bodyClass}">
<a class="skip" href="#main">skip to content</a>
<main id="main" class="desktop">${body}</main>
<nav class="taskbar" aria-label="taskbar">
<button class="start" type="button" aria-haspopup="menu" aria-expanded="false">${icon('moon', 1)}<b>pawan</b></button>
<div class="tasks">${tasks}</div>
<div class="tray">
${ctx.music ? `<button class="tray-music" type="button" aria-pressed="false" aria-label="play music" title="${esc(ctx.musicName)}"><span class="note">♫</span><span class="eq" aria-hidden="true"><i></i><i></i><i></i><i></i></span></button>` : ''}
<button class="tray-theme" type="button" aria-label="switch day and night"><span class="sun">☼</span><span class="moon">☾</span></button>
<time class="clock" aria-label="time">--:--</time>
</div>
</nav>
<div class="startmenu" role="menu" hidden>
<div class="side"><span>PAWAN.SYS</span></div>
<ul>
<li><a role="menuitem" href="/">${icon('writing', 2)}<span>writing</span></a></li>
<li><a role="menuitem" href="/papers/">${icon('papers', 2)}<span>papers</span></a></li>
${ctx.books.length ? `<li><a role="menuitem" href="/books/">${icon('books', 2)}<span>books</span></a></li>` : ''}
<li><a role="menuitem" href="https://pawann.dev">${icon('web', 2)}<span>pawann.dev</span></a></li>
<li><a role="menuitem" href="https://github.com/Cintu07">${icon('terminal', 2)}<span>github</span></a></li>
<li><a role="menuitem" href="/feed.xml">${icon('eye', 2)}<span>feed</span></a></li>
<li class="sep"></li>
<li><button role="menuitem" type="button" data-action="theme">${icon('moon', 2)}<span>day / night</span></button></li>
<li><button role="menuitem" type="button" data-action="saver">${icon('seams', 2)}<span>screensaver</span></button></li>
</ul>
</div>
${ctx.music ? `<audio id="music" src="${ctx.music}" preload="none" loop></audio>` : ''}
<canvas class="trail" aria-hidden="true"></canvas>
<div class="saver" hidden><canvas></canvas><p>move the mouse to come back</p></div>
<script type="module" src="/static/os.js"></script>
</body>
</html>`;
}

// a book as a 3D object: cover, spine, page edge, top, back. size is 'small' (shelf) or 'big'.
function book3d(b, size, href) {
  const meta = [b.year, b.pages ? b.pages + ' pages' : ''].filter(Boolean).join(' · ');
  const cover = `<span class="cover"><span class="ck">PAWAN.SYS PRESS</span><b class="ct">${esc(b.title)}</b>${size === 'big' && b.subtitle ? `<span class="cs">${esc(b.subtitle)}</span>` : ''}${mask(b.art, 'cart')}<span class="cy">${esc(meta)}</span></span>`;
  const inside = size === 'big' ? `<span class="face page"><span class="pg"><span class="ck">ex libris · pawan</span><span class="pb">${esc(String(b.blurb).split('\n\n')[0])}</span>${b.pdf ? '<span class="pl">click again to read the pdf ⟶</span>' : ''}</span></span>` : '';
  return `<${href ? `a href="${href}"` : 'button type="button"'} class="book3d ${size}" aria-label="${esc(b.title)}"${b.pdf ? ` data-pdf="${b.pdf}"` : ''}>
<span class="b3">${inside}<span class="face front"><span class="hinge">${cover}<span class="inner"></span></span></span><span class="face spine"><b>${esc(b.title)}</b><i>${esc(b.year ?? '')}</i></span><span class="face edge"></span><span class="face top"></span><span class="face back"></span></span>
</${href ? 'a' : 'button'}>`;
}

// ---------------------------------------------------------------- pages

const DESKTOP_ICONS = (ctx) => `<nav class="icons" aria-label="desktop">
<a class="ico" href="/#writing">${icon('writing')}<span>writing.txt</span></a>
<a class="ico" href="/papers/">${icon('papers')}<span>papers.pdf</span></a>
${ctx.books.length ? `<a class="ico" href="/books/">${icon('books')}<span>books.lnk</span></a>` : ''}
<a class="ico" href="https://github.com/Cintu07/seams">${icon('seams')}<span>seams.exe</span></a>
<a class="ico" href="https://pawann.dev">${icon('web')}<span>pawann.dev</span></a>
<button class="ico bin-ico" type="button" data-action="bin"><span class="empty-bin">${icon('bin')}</span><span class="full-bin">${icon('binFull')}</span><span>recycle bin</span></button>
</nav>`;

export function home(ctx) {
  const { posts, papers, favourites, books } = ctx;
  const latest = posts[0];
  const welcome = win({
    id: 'welcome', title: 'pawan.sys', palette: 'paper', glyph: icon('moon', 1), cls: 'w-welcome',
    menu: [['GitHub', 'https://github.com/Cintu07'], ['X', 'https://x.com/pawankalyandev'], ['pawann.dev', 'https://pawann.dev'], ['Feed', '/feed.xml']],
    body: `<figure class="banner"><canvas class="anime" role="img" aria-label="a late summer evening in a 90s anime: a tall cloud, power lines, a train going by"></canvas><span class="stamp">1996.08.13 &nbsp;夏の終わり</span></figure>
<div class="intro-pc">
<div>
<p class="say">i'm pawan. i build database and inference stuff and break it a lot. this is where i write down why.</p>
<dl class="rows-pc">
<div><dt>good at</dt><dd>ml infra, databases, inference</dd></div>
<div><dt>languages</dt><dd>rust, go, typescript, c</dd></div>
<div><dt>latest</dt><dd><a href="${latest.url}">${esc(latest.title)}</a></dd></div>
</dl>
</div>
${mask(ctx.art.hero, 'heroart', 'a 1-bit drawing of an old CRT computer on a desk, with a keyboard, floppy disks and a mug')}
</div>
<div class="hello">
<div class="intro">
<p class="kick"><span class="pill">HELLO</span><span class="pill">${posts.length} POSTS</span></p>
<h1>i build database and inference stuff and <u>break</u> it a lot.</h1>
<p class="lede">this is where i write down why. every number in a post was printed by a program that ran.</p>
</div>
<dl class="facts">
<div><dt>good at</dt><dd>ml infra, databases, inference</dd></div>
<div><dt>languages</dt><dd>rust, go, typescript, c</dd></div>
<div><dt>status</dt><dd>alive, compiling</dd></div>
<div><dt>written</dt><dd>${posts.length} posts, ${(posts.reduce((n, p) => n + p.words, 0) / 1000).toFixed(1)}k words</dd></div>
<div><dt>latest</dt><dd><a href="${latest.url}">${esc(latest.title)}</a></dd></div>
</dl>
</div>`,
    status: [`${posts.length} object(s)`, `${(posts.reduce((n, p) => n + p.words, 0) / 1000).toFixed(1)}k words`, 'ready'],
  });
  const room = win({
    id: 'room', title: 'room.exe', palette: 'night', glyph: icon('seams', 1), cls: 'w-room',
    body: `<canvas class="room" width="240" height="180" role="img" aria-label="an isometric 1-bit room: a desk with a computer, rain on the window, someone asleep"></canvas>
<p class="ticker"><span>(-_-)zzz</span> ▷ 0:00/∞ ——●—— now: <a href="${latest.url}">${esc(latest.title)}</a></p>`,
  });
  const writing = win({
    id: 'writing', title: `writing.txt — ${posts.length} posts`, palette: 'paper', glyph: icon('writing', 1), cls: 'w-writing',
    menu: [['Newest', null, 'sort-new'], ['Oldest', null, 'sort-old'], ['Quick reads', null, 'sort-short'], ['Random', null, 'sort-random']],
    body: `<div class="cards">${posts.map(card).join('')}</div>`,
    status: [`${posts.length} object(s)`, `newest: ${pretty(latest.date)}`, 'all programs ran'],
  });
  const paperRows = papers.map((p) => `<li><a href="${p.url}"><span class="t">${esc(p.title)}</span><span class="d">${esc(p.codeName ?? '')}</span></a><p>${esc(p.note ?? '')}</p></li>`).join('');
  const papersWin = win({
    id: 'papers', title: 'papers.pdf', palette: 'moss', glyph: icon('papers', 1), cls: 'w-papers',
    body: `<p class="small">research papers i implement, with the code.</p><ul class="rows">${paperRows}</ul><a class="more" href="/papers/">all papers ⟶</a>`,
    status: [`${papers.length} implemented`, `${favourites.length} loved`],
  });
  const booksWin = books.length ? win({
    id: 'books', title: 'books.lnk', palette: 'clay', glyph: icon('books', 1), cls: 'w-books',
    body: `<div class="shelf3d">${books.map((b) => book3d(b, 'small', `/books/#${b.slug}`)).join('')}</div><p class="small shelfnote">hover a book to pull it off the shelf</p>`,
    status: [`${books.length} book(s)`, 'free pdf'],
  }) : '';
  const bin = win({
    id: 'bin', title: 'Recycle Bin', palette: 'night', glyph: icon('bin', 1), cls: 'w-bin',
    menu: [['Restore all', null, 'restore-all']],
    body: `<div class="binlist"><p class="head"><span>Name</span><span>Original Location</span></p><ul class="binitems"></ul><p class="empty">bugs i shipped are fixed. nothing in here.</p></div><p class="binbtns"><button class="btn restore-all" type="button">Restore all</button></p>`,
    status: ['<span class="bincount">0 object(s)</span>', '0 bytes'],
  });
  ctx.tasks = [['welcome', 'pawan.sys', 'moon'], ['writing', 'writing.txt', 'writing'], ['room', 'room.exe', 'seams'], ['papers', 'papers.pdf', 'papers']];
  return page({
    title: NAME, description: TAGLINE, path: '/', ctx, bodyClass: 'home',
    body: `${DESKTOP_ICONS(ctx)}<div class="wins">${welcome}${writing}<aside class="col side">${room}${papersWin}${booksWin}${bin}</aside></div>`,
  });
}

export function article(p, ctx) {
  const others = ctx.posts.filter((o) => o !== p);
  const i = ctx.posts.indexOf(p);
  const next = ctx.posts[i + 1], prev = ctx.posts[i - 1];
  const toc = p.toc.length ? win({
    id: 'toc', title: 'contents', palette: 'paper', glyph: icon('writing', 1), cls: 'w-toc',
    body: `<ol>${p.toc.map((t) => `<li><a href="#${t.id}">${esc(t.text)}</a></li>`).join('')}</ol>`,
  }) : '';
  const props = win({
    id: 'props', title: `${p.slug}.md properties`, palette: p.palette, glyph: icon('eye', 1), cls: 'w-props',
    body: `<dl class="sheet">
<div><dt>Type</dt><dd>Markdown document</dd></div>
<div><dt>Created</dt><dd>${pretty(p.date)}</dd></div>
<div><dt>Size</dt><dd>${p.words.toLocaleString('en')} words</dd></div>
<div><dt>Reading</dt><dd>${p.minutes} min</dd></div>
<div><dt>Tags</dt><dd>${esc(p.tags.join(', '))}</dd></div>
<div><dt>Attributes</dt><dd>☑ read-only ☑ ran every program</dd></div>
</dl>`,
  });
  const reader = win({
    id: 'reader', title: `${p.slug}.md — Reader`, palette: 'paper', glyph: icon('writing', 1), cls: 'w-reader',
    menu: [['Home', '/'], ['Top', '#main'], ['Copy link', null, 'copy-link'], ['Night', null, 'theme']],
    body: `<div class="hero pal-${p.palette}">${mask(p.art, 'art', `generated art for ${p.title}`)}<span class="caption">fig. 0 — generated for this post, 1 bit</span></div>
<header class="head">
<p class="kick">${tagPills(p.tags)}</p>
<h1>${titleWithUnderline(p.title)}</h1>
<p class="byline"><time datetime="${p.iso}">${caps(p.date)}</time><span>${p.minutes} MIN READ</span><span>${p.words.toLocaleString('en')} WORDS</span></p>
${p.standfirst ? `<p class="standfirst">${p.standfirst}</p>` : ''}
</header>
<article class="prose">${p.html}</article>
<p class="eof">◆ end of file ◆</p>
${mask(ctx.art.oyster ?? ctx.art.wings, 'end')}
<nav class="pager">${next ? `<a class="prev" href="${next.url}"><small>◀ older</small>${esc(next.title)}</a>` : '<span></span>'}${prev ? `<a class="next" href="${prev.url}"><small>newer ▶</small>${esc(prev.title)}</a>` : '<span></span>'}</nav>`,
    status: [`${p.minutes} min read`, `${p.words.toLocaleString('en')} words`, `<span class="progress">0%</span>`],
  });
  const more = win({
    id: 'more', title: 'more writing', palette: 'night', glyph: icon('writing', 1), cls: 'w-more',
    body: `<ul class="rows">${others.slice(0, 6).map((o) => `<li><a href="${o.url}"><span class="t">${esc(o.title)}</span><span class="d">${pretty(o.date)}</span></a></li>`).join('')}</ul>`,
  });
  ctx.tasks = [['reader', `${p.slug}.md`, 'writing']];
  return page({
    title: p.title, description: p.description, path: p.url, ctx, bodyClass: 'post', og: `/assets/og/${p.slug}.png`,
    body: `${DESKTOP_ICONS(ctx)}<div class="wins">${reader}<aside class="col side">${toc}${props}${more}</aside></div>`,
  });
}

export function papersPage(ctx) {
  const row = (p) => `<li class="paper"><a class="t" href="${p.url}">${esc(p.title)}</a><p class="by">${esc(p.authors ?? '')} · ${esc(p.venue ?? '')}</p><p>${esc(p.note ?? '')}</p>${p.code ? `<a class="code" href="${p.code}">${icon('terminal', 1)} ${esc(p.codeName ?? 'code')}</a>` : ''}</li>`;
  const impl = win({ id: 'impl', title: 'papers i implement', palette: 'moss', glyph: icon('papers', 1), cls: 'w-list', body: `<ul class="papers">${ctx.papers.map(row).join('')}</ul>`, status: [`${ctx.papers.length} object(s)`] });
  const loved = ctx.favourites.length ? win({ id: 'favourites', title: 'papers i love', palette: 'lilac', glyph: icon('eye', 1), cls: 'w-list', body: `<ul class="papers">${ctx.favourites.map(row).join('')}</ul>`, status: [`${ctx.favourites.length} object(s)`] }) : '';
  ctx.tasks = [['impl', 'papers', 'papers']];
  return page({ title: 'papers', description: 'research papers i implement, with the code.', path: '/papers/', ctx, bodyClass: 'list', body: `${DESKTOP_ICONS(ctx)}<div class="wins">${impl}${loved}</div>` });
}

export function booksPage(ctx) {
  const body = ctx.books.map((b) => win({
    id: b.slug, title: `${b.slug}.pdf`, glyph: icon('books', 1), cls: 'w-book',
    body: `<div class="bookrow"><div class="stage">${book3d(b, 'big')}<p class="caption">click the book to open it</p></div><div><h2>${esc(b.title)}</h2>${b.subtitle ? `<p class="sub">${esc(b.subtitle)}</p>` : ''}${String(b.blurb).split('\n\n').map((t) => `<p>${esc(t)}</p>`).join('')}<p class="links">${b.pdf ? `<a class="btn" href="${b.pdf}">⤓ read the pdf</a>` : ''}${b.code ? `<a class="btn" href="${b.code}">⤓ source</a>` : ''}</p></div></div>`,
    status: [b.year ?? '', b.pages ? `${b.pages} pages` : 'free pdf'],
  })).join('');
  ctx.tasks = [];
  return page({ title: 'books', description: 'books i wrote.', path: '/books/', ctx, bodyClass: 'list books', body: `${DESKTOP_ICONS(ctx)}<div class="wins">${body}</div>` });
}

export function notFound(ctx) {
  ctx.tasks = [];
  const posts = ctx.posts.map((p) => p.url);
  const err = win({
    id: 'error', title: 'PAWAN.SYS — Fatal Exception', glyph: icon('bin', 1), cls: 'w-error',
    body: `<div class="errbox"><span class="x">×</span><div><p><b>A fatal exception 404 has occurred at <code class="where">this address</code>.</b></p><p>the page you asked for is not here. it may have moved, or it never existed. move the mouse and watch the error follow you.</p></div></div>
<pre class="dump">EAX=00000404  EBX=DEADBEEF  ECX=0000CAFE
EIP=0000:0404  stack: home &gt; writing &gt; ???</pre>
<p class="btns"><a class="btn" href="/">OK, take me home</a><a class="btn random" href="${posts[0]}" data-posts="${posts.join(' ')}">Random post</a></p>`,
  });
  return page({ title: 'not found', description: 'page not found.', path: '/404.html', ctx, bodyClass: 'list oops', body: `<div class="big404" aria-hidden="true">404</div>${DESKTOP_ICONS(ctx)}<div class="wins center">${err}</div>` });
}

// 1200x630 link-preview card, screenshotted by build/og.mjs into assets/og/
export function ogCard({ title, kicker, art, palette = 'paper', foot }) {
  return `<!doctype html><html data-theme="day"><head><meta charset="utf-8"><meta name="robots" content="noindex"><link rel="stylesheet" href="/static/site.css">
<style>html,body{margin:0;width:1200px;height:630px;overflow:hidden}body{padding:44px 52px;background-size:6px 6px}
.og{display:grid;grid-template-columns:1fr 470px;height:100%;animation:none!important}.og .body{display:grid;grid-template-columns:1fr 470px;gap:30px;padding:30px 34px;align-items:center}
.og h1{font:600 54px/1.06 var(--slab);margin:16px 0 18px;letter-spacing:-.015em}.og .k{display:flex;gap:8px;flex-wrap:wrap}.og .pill{font-size:17px}
.og .foot{font:19px/1.3 var(--ui);color:var(--soft)}.og .artbox{background:var(--paper);color:var(--ink);border:2px solid var(--chrome);padding:16px}</style></head>
<body><section class="win pal-paper og" style="display:flex"><header class="bar"><span class="title">pawan.sys — ${esc(kicker)}</span><span class="ctl"><button>_</button><button>□</button><button>×</button></span></header>
<div class="body"><div><p class="k">${foot.tags.map((t) => `<span class="pill">${esc(t)}</span>`).join('')}</p><h1>${title}</h1><p class="foot">${esc(foot.line)}</p></div>
<div class="artbox pal-${palette}">${mask(art)}</div></div></section></body></html>`;
}
export { titleWithUnderline, caps, pretty };
