// Photographs the /og/ pages into assets/og/*.png (1200x630) for link previews.
// Run after a build, with the dev server up:  node build/serve.mjs & node build/og.mjs
// The PNGs are committed, so the site build itself needs no browser.
import { chromium } from 'playwright-core';
import { readdirSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const base = process.env.OG_BASE ?? 'http://localhost:4321';
const names = readdirSync(join(root, 'dist/og'));
mkdirSync(join(root, 'assets/og'), { recursive: true });
const browser = await chromium.launch({ channel: process.env.OG_CHANNEL ?? 'msedge' });
const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
for (const name of names) {
  await page.goto(`${base}/og/${name}/`);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: join(root, 'assets/og', `${name}.png`) });
  console.log('og', name);
}
await browser.close();
