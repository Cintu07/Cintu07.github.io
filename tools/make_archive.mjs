// Copies the built window-style site (next/dist) to <out>, with every root-relative URL moved under /archive/.
// It is kept as a museum piece: no sitemap, no feed, noindex.
// A file that the live site already serves byte for byte (the book pdfs, the song, post images) is not copied:
// the archive links to the live copy, so the repo does not carry 50 MB twice.
//   node make_archive.mjs <next/dist> <out> [live site root, e.g. v3]
import { readdirSync, statSync, readFileSync, writeFileSync, mkdirSync, copyFileSync, rmSync, existsSync } from 'fs';
import { join, extname, relative, sep } from 'path';
const [src, out, live] = process.argv.slice(2);
const P = '/archive';
const top = readdirSync(src).filter((f) => !['sitemap.xml', 'robots.txt', 'feed.xml'].includes(f));
const names = top.map((f) => f.replace(/[.]/g, '\\.')).join('|');
// "/posts/x", '/assets/..', (/og/..), url(/static/..), and a bare "/" link
const re = new RegExp(`(["'(=\\s,:])/(?=(?:${names})(?:[/"'?#)\\s]|$))`, 'g');

// assets the live site has, identical: path under assets/ -> true
const shared = new Set();
if (live) {
  const scan = (dir) => {
    for (const f of readdirSync(dir)) {
      const a = join(dir, f);
      if (statSync(a).isDirectory()) { scan(a); continue; }
      const rel = relative(join(src, 'assets'), a).split(sep).join('/');
      const mine = join(live, 'assets', rel);
      if (existsSync(mine) && statSync(mine).size === statSync(a).size && readFileSync(mine).equals(readFileSync(a))) shared.add(rel);
    }
  };
  scan(join(src, 'assets'));
}

rmSync(out, { recursive: true, force: true });
let files = 0, rewrites = 0, skipped = 0, skippedBytes = 0;
const walk = (from, to) => {
  mkdirSync(to, { recursive: true });
  for (const f of readdirSync(from)) {
    if (from === src && !top.includes(f)) continue;
    const a = join(from, f), b = join(to, f);
    if (statSync(a).isDirectory()) { walk(a, b); continue; }
    const relAsset = relative(join(src, 'assets'), a).split(sep).join('/');
    if (shared.has(relAsset)) { ++skipped; skippedBytes += statSync(a).size; continue; }
    ++files;
    if (!['.html', '.css', '.js', '.json', '.xml', '.webmanifest'].includes(extname(f))) { copyFileSync(a, b); continue; }
    let s = readFileSync(a, 'utf8');
    s = s.replace(re, (m, c) => { ++rewrites; return `${c}${P}/`; });
    s = s.replace(/(href=["'])\/(["'#])/g, (m, a1, a2) => { ++rewrites; return `${a1}${P}/${a2}`; });
    s = s.replace(/\['Home', '\/'\]/g, `['Home', '${P}/']`).replace(/"href_matches":"\/\*"/g, `"href_matches":"${P}/*"`).replace(/"href_matches":"\/assets\/\*"/g, `"href_matches":"${P}/assets/*"`);
    s = s.replace(/https:\/\/cintu07\.github\.io\/(?!archive)/g, `https://cintu07.github.io${P}/`);
    // shared files point back at the live site's copy
    for (const rel of shared) {
      for (const form of new Set([rel, encodeURI(rel)])) s = s.split(`${P}/assets/${form}`).join(`/assets/${form}`);
    }
    if (extname(f) === '.html') s = s.replace('<head>', '<head><meta name="robots" content="noindex">');
    writeFileSync(b, s);
  }
};
walk(src, out);
console.log(`${files} files, ${rewrites} urls moved under ${P}/, ${skipped} files (${(skippedBytes / 2 ** 20).toFixed(1)} MiB) shared with the live site`);
