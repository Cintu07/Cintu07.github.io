# pawan.sys

my blog as a 1-bit desktop. same posts as before, same urls (`/posts/<slug>/`), new everything else.

## writing a post

same as the old site: drop a markdown file in `content/posts/` with front matter (`title`, `date`,
`description`, `tags`, optional `cover`). a leading `>` quote becomes the standfirst.
`{: .code-caption }` under a line still makes it a caption.

every post gets its own generated picture: a small 3d scene in `build/art.mjs`, rendered by a
raymarcher and dithered to 1 bit. a post without its own scene gets a moon. add a scene keyed by
the post's slug to give it one.

## building

```
npm install
node build/build.mjs      # writes dist/
node build/serve.mjs      # http://localhost:4321/
```

link-preview images live in `assets/og/` and are committed. after adding a post, with the server
running: `node build/og.mjs` (needs edge or chrome), then build again.

## how it looks the way it does

- every image is a 1-bit mask; css paints it with the window's ink, so one file works on cream paper
  by day and black glass at night (`build/dither.mjs`: atkinson, floyd-steinberg, bayer, halftone)
- windows take one paper/ink pair: paper, lilac, night, moss, clay, blueprint (`static/site.css`)
- the moon, the room, the screensaver and the cursor trail are drawn pixel by pixel with no
  smoothing (`static/live.js`)
- with scripts off it is a plain readable document

fonts: et book (mit), cascadia code (ofl), vt323, dotgothic16, zilla slab, silkscreen (ofl).
