// Serves dist/ like GitHub Pages would: directories get index.html, misses get 404.html.
//   node build/serve.mjs [port]
import { createServer } from 'http';
import { createReadStream, statSync, existsSync } from 'fs';
import { join, normalize, extname, dirname } from 'path';
import { fileURLToPath } from 'url';
const dist = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2', '.xml': 'application/xml', '.pdf': 'application/pdf', '.mp3': 'audio/mpeg', '.mp4': 'video/mp4', '.gif': 'image/gif' };
function listen(port, tries) {
  const server = createServer((req, res) => {
    let path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname)).replace(/^[\\/]+/, '');
    if (path.startsWith('..')) return res.writeHead(400).end();
    let file = join(dist, path);
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html');
    const found = existsSync(file) && statSync(file).isFile();
    if (!found) file = join(dist, '404.html');
    res.writeHead(found ? 200 : 404, { 'content-type': types[extname(file)] ?? 'application/octet-stream', 'cache-control': 'no-store' });
    createReadStream(file).pipe(res);
  });
  server.once('error', (e) => { if (e.code === 'EADDRINUSE' && tries) listen(port + 1, tries - 1); else throw e; });
  server.listen(port, () => console.log(`http://localhost:${port}/`));
}
listen(Number(process.argv[2] ?? 4321), 10);
