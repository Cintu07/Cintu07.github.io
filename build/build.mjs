// Builds the site into dist/. Same content format as the old site: content/posts/*.md with front
// matter, content/papers.json, favourites.json, books.json. Same post URLs: /posts/<slug>/.
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, cpSync, rmSync, statSync } from 'fs';
import { join, dirname, basename, extname } from 'path';
import { fileURLToPath } from 'url';
import { createHash } from 'crypto';
import { marked } from 'marked';
import hljs from 'highlight.js';
import sharp from 'sharp';
import { render, sceneFor } from './art.mjs';
import { loadGray, atkinson, writeMask } from './dither.mjs';
import { page, home, article, papersPage, booksPage, notFound, PALETTES, paletteFor, ogCard, titleWithUnderline, caps } from './pages.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist'), CONTENT = join(ROOT, 'content'), CACHE = join(ROOT, '.cache', 'art');
export const SITE = 'https://cintu07.github.io';

const write = (path, text) => {
  const file = join(DIST, path.endsWith('/') ? path + 'index.html' : path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
};
const slugify = (s) => s.toLowerCase().replace(/<[^>]+>/g, '').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-');

// ---------------------------------------------------------------- posts

function frontmatter(text) {
  const m = text.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!m) return { meta: {}, body: text };
  const meta = {};
  for (const line of m[1].split('\n')) {
    const i = line.indexOf(':');
    if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return { meta, body: text.slice(m[0].length) };
}

marked.use({
  gfm: true,
  renderer: {
    heading({ tokens, depth }) {
      const text = this.parser.parseInline(tokens);
      const id = slugify(text);
      return `<h${depth} id="${id}"><a class="anchor" href="#${id}" aria-hidden="true">#</a>${text}</h${depth}>\n`;
    },
    code({ text, lang }) {
      const language = (lang || '').trim().split(/\s+/)[0];
      const html = language && hljs.getLanguage(language) ? hljs.highlight(text, { language }).value : hljs.highlightAuto(text).value;
      const label = language || 'text';
      return `<figure class="code win pal-night"><figcaption class="bar"><span class="title">C:\\&gt; ${label}</span><button class="copy" type="button" aria-label="copy code">copy</button></figcaption><pre><code class="hljs language-${label}">${html}</code></pre></figure>\n`;
    },
    image({ href, title, text }) {
      const cap = title || '';
      return `<img src="${href}" alt="${text.replace(/"/g, '&quot;')}" loading="lazy" decoding="async"${cap ? ` title="${cap}"` : ''}>`;
    },
  },
});

// python-markdown style "{: .class }" on its own line applies the class to the paragraph before it
function attrLists(html) {
  // the paragraph text may not contain another <p>, so a match never spans paragraphs
  const one = '((?:(?!<\\/?p[ >])[\\s\\S])*?)';
  return html
    .replace(new RegExp(`<p>${one}<\\/p>\\s*<p>\\{:\\s*\\.([\\w-]+)\\s*\\}<\\/p>`, 'g'), '<p class="$2">$1</p>')
    .replace(new RegExp(`<p>${one}\\n\\{:\\s*\\.([\\w-]+)\\s*\\}<\\/p>`, 'g'), '<p class="$2">$1</p>');
}

function loadPosts() {
  const dir = join(CONTENT, 'posts');
  return readdirSync(dir).filter((f) => f.endsWith('.md')).map((f) => {
    const { meta, body } = frontmatter(readFileSync(join(dir, f), 'utf8').replace(/\r\n/g, '\n'));
    const slug = basename(f, '.md');
    let text = body.trim(), standfirst = '';
    const lead = text.match(/^((?:>.*\n?)+)/);
    if (lead) { standfirst = marked.parseInline(lead[1].replace(/^>\s?/gm, '').trim()); text = text.slice(lead[0].length); }
    const html = attrLists(marked.parse(text));
    const words = text.split(/\s+/).length;
    const toc = [...html.matchAll(/<h2 id="([^"]+)">(?:<a[^>]*>#<\/a>)?([\s\S]*?)<\/h2>/g)].map((m) => ({ id: m[1], text: m[2].replace(/<[^>]+>/g, '').replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>') }));
    const date = new Date(meta.date + 'T00:00:00Z');
    return {
      slug, title: meta.title, description: meta.description || '', standfirst: standfirst || meta.description || '',
      tags: (meta.tags || '').split(',').map((t) => t.trim().toLowerCase()).filter(Boolean),
      date, iso: meta.date, cover: meta.cover || '', html, words, minutes: Math.max(1, Math.round(words / 230)), toc,
      url: `/posts/${slug}/`,
    };
  }).sort((a, b) => b.date - a.date);
}

// ---------------------------------------------------------------- art

const artVersion = createHash('sha1').update(readFileSync(join(ROOT, 'build/art.mjs'))).update(readFileSync(join(ROOT, 'build/dither.mjs'))).digest('hex').slice(0, 10);

// one generated scene per post, dithered to a mask; cached by the renderer's source
async function postArt(slug, w = 400, h = 250) {
  mkdirSync(CACHE, { recursive: true });
  const cached = join(CACHE, `${slug}-${w}x${h}-${artVersion}.png`);
  if (!existsSync(cached)) {
    const t0 = Date.now();
    const gray = render(sceneFor(slug), w, h);
    await writeMask(atkinson({ gray, w, h }), cached);
    console.log(`  art ${slug} ${Date.now() - t0} ms`);
  }
  const out = `/assets/art/${slug}.png`;
  mkdirSync(join(DIST, 'assets/art'), { recursive: true });
  cpSync(cached, join(DIST, out));
  return { src: out, w, h };
}

// the old site's engravings (black ink on transparency) become masks too
async function engravings() {
  const manifest = JSON.parse(readFileSync(join(ROOT, 'assets/art/manifest.json'), 'utf8'));
  const out = {};
  for (const [name, info] of Object.entries(manifest)) {
    if (!info.ink) continue;
    const { data, info: m } = await sharp(join(ROOT, `assets/art/${name}.webp`)).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
    const ink = new Uint8Array(m.width * m.height);
    for (let i = 0; i < ink.length; ++i) {
      const a = data[i * 4 + 3], lum = (data[i * 4] + data[i * 4 + 1] + data[i * 4 + 2]) / 3;
      ink[i] = a > 110 && lum < 140 ? 1 : 0;
    }
    await writeMask({ ink, w: m.width, h: m.height }, join(DIST, `assets/art/${name}.png`));
    out[name] = { src: `/assets/art/${name}.png`, w: m.width, h: m.height };
  }
  return out;
}

// a photo or cover dithered with Atkinson; dark images are inverted so their content becomes the ink
async function ditherPhoto(src, name, width = 320) {
  const g = await loadGray(join(ROOT, src.replace(/^\//, '')), width, { contrast: 1.25 });
  const mean = g.gray.reduce((a, b) => a + b, 0) / g.gray.length;
  if (mean < 0.45) for (let i = 0; i < g.gray.length; ++i) g.gray[i] = 1 - g.gray[i];
  const out = `/assets/art/${name}.png`;
  await writeMask(atkinson(g), join(DIST, out));
  return { src: out, w: g.w, h: g.h };
}

// ---------------------------------------------------------------- feeds

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function feed(posts) {
  const items = posts.map((p) => `<entry><title>${esc(p.title)}</title><link href="${SITE}${p.url}"/><id>${SITE}${p.url}</id><updated>${p.iso}T00:00:00Z</updated><summary>${esc(p.description)}</summary></entry>`).join('');
  return `<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>pawan</title><link href="${SITE}/"/><id>${SITE}/</id><updated>${posts[0].iso}T00:00:00Z</updated>${items}</feed>`;
}

// ---------------------------------------------------------------- main

async function main() {
  const t0 = Date.now();
  rmSync(DIST, { recursive: true, force: true });
  mkdirSync(DIST, { recursive: true });
  for (const dir of ['fonts', 'img', 'books', 'music']) cpSync(join(ROOT, 'assets', dir), join(DIST, 'assets', dir), { recursive: true });
  cpSync(join(ROOT, 'static'), join(DIST, 'static'), { recursive: true });

  const posts = loadPosts();
  console.log(`${posts.length} posts`);
  for (const p of posts) { p.art = await postArt(p.slug); p.palette = paletteFor(p.slug); }
  const art = await engravings();
  art.hero = await postArt('hero', 440, 380);
  const papers = JSON.parse(readFileSync(join(CONTENT, 'papers.json'), 'utf8'));
  const favourites = existsSync(join(CONTENT, 'favourites.json')) ? JSON.parse(readFileSync(join(CONTENT, 'favourites.json'), 'utf8')) : [];
  const books = JSON.parse(readFileSync(join(CONTENT, 'books.json'), 'utf8'));
  for (const b of books) {
    b.slug = slugify(b.title);
    b.art = await postArt(`book-${b.slug}`, 260, 300);
  }
  // the first audio file in assets/music plays from the tray button
  const music = readdirSync(join(ROOT, 'assets/music')).find((f) => /\.(mp3|ogg|m4a|opus)$/i.test(f));
  const ctx = { posts, papers, favourites, books, art, music: music ? `/assets/music/${encodeURIComponent(music)}` : '', musicName: music ? basename(music, extname(music)).replace(/-/g, ' ') : '' };

  write('/', home(ctx));
  for (const p of posts) write(p.url, article(p, ctx));
  write('/papers/', papersPage(ctx));
  write('/books/', booksPage(ctx));
  // the old site had a page per book; keep those links working
  for (const b of books) write(`/books/${b.slug}/`, `<!doctype html><meta charset="utf-8"><title>${esc(b.title)}</title><link rel="canonical" href="${SITE}/books/"><meta http-equiv="refresh" content="0; url=/books/#${b.slug}"><a href="/books/#${b.slug}">${esc(b.title)}</a>`);
  write('/404.html', notFound(ctx));
  write('/feed.xml', feed(posts));
  write('/sitemap.xml', `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${['/', '/papers/', '/books/', ...posts.map((p) => p.url)].map((u) => `<url><loc>${SITE}${u}</loc></url>`).join('')}</urlset>`);
  write('/.nojekyll', '');
  // the old site published these too
  write('/robots.txt', `User-agent: *\nAllow: /\nSitemap: ${SITE}/sitemap.xml\n`);
  write('/posts.json', JSON.stringify(posts.map((p) => ({ title: p.title, url: SITE + p.url, date: p.iso, description: p.description, tags: p.tags, minutes: p.minutes }))));
  // link-preview cards: pages for build/og.mjs to photograph, and the photos it made earlier
  for (const p of posts) write(`/og/${p.slug}/`, ogCard({ title: titleWithUnderline(p.title), kicker: `${p.slug}.md`, art: p.art, palette: p.palette, foot: { tags: p.tags.slice(0, 3), line: `${caps(p.date)} · ${p.minutes} MIN READ · cintu07.github.io` } }));
  write('/og/home/', ogCard({ title: 'i build database and inference stuff and <u>break</u> it a lot.', kicker: 'welcome', art: art.hero, palette: 'paper', foot: { tags: ['writing', 'papers', 'books'], line: 'pawan · cintu07.github.io' } }));
  if (existsSync(join(ROOT, 'assets/og'))) cpSync(join(ROOT, 'assets/og'), join(DIST, 'assets/og'), { recursive: true });
  console.log(`built in ${Date.now() - t0} ms`);
}

main().catch((e) => { console.error(e); process.exit(1); });
