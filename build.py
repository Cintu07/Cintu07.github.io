"""Builds the site from content/ into dist/, which the pages workflow deploys.

    pip install -r requirements.txt
    python build.py
"""

import datetime
import email.utils
import html
import json
import re
import shutil
import urllib.parse
from pathlib import Path

import markdown

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
DIST = ROOT / "dist"
SITE = "https://cintu07.github.io"
NAME = "pawan"
TAGLINE = "long posts on ml infra, databases and inference, and the bugs in between."
GOOD_AT = "ml infra, databases, inference"
LANGUAGES = "rust, go, typescript"
# Moving between pages swaps the header, the page and the footer in place instead of loading a new document.
# That is what lets the song play on through a click: the player sits outside what is swapped, so the browser
# never tears it down. A link is fetched when it is hovered or touched, so by the click it is usually here.
# Anything that is not one of these pages (a download, another site, a modified click) is left to the browser,
# and so is anything that goes wrong, which then loads the page the ordinary way.
NAV_JS = r"""(function () {
  if (!window.fetch || !window.DOMParser || !history.pushState) return;
  var SWAP = ["header", "main", "footer"];
  var HEAD = 'meta[name="description"], link[rel="canonical"], meta[property^="og:"], meta[name^="twitter:"], script[type="application/ld+json"]';
  var pages = {}, current = location.pathname + location.search, turn = 0, timer;
  // a swap is not a page load, so the browser has nothing to restore the scroll from: it is kept here
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  function target(a) {
    if (!a) return null;
    var href = a.getAttribute("href"), to = a.getAttribute("target");
    if (!href || a.hasAttribute("download") || (to && to !== "_self")) return null;
    var u = new URL(href, location.href);
    if (u.origin !== location.origin || /\.[a-z0-9]+$/i.test(u.pathname) || u.pathname.indexOf("/archive") === 0) return null;
    return u;
  }
  function load(u) {
    var key = u.pathname + u.search, hit = pages[key];
    if (hit && Date.now() - hit.at < 300000) return hit.p;
    var p = fetch(u.href).then(function (r) {
      if (!r.ok || (r.headers.get("content-type") || "").indexOf("text/html") < 0) throw new Error("not a page");
      return r.text().then(function (html) { return { html: html, url: r.url || u.href }; });
    });
    pages[key] = { p: p, at: Date.now() };
    p.catch(function () { delete pages[key]; });
    return p;
  }
  function parse(html) {
    var next = new DOMParser().parseFromString(html, "text/html");
    return SWAP.every(function (s) { return document.querySelector(s) && next.querySelector(s); }) ? next : null;
  }
  function apply(next, u, how) {
    if (how === "push") {
      history.replaceState({ y: window.scrollY }, "");
      history.pushState({ y: 0 }, "", u.href);
    }
    current = u.pathname + u.search;
    document.title = next.title;
    document.head.querySelectorAll(HEAD).forEach(function (e) { e.remove(); });
    next.head.querySelectorAll(HEAD).forEach(function (e) { document.head.appendChild(document.importNode(e, true)); });
    SWAP.forEach(function (s) { document.querySelector(s).replaceWith(document.importNode(next.querySelector(s), true)); });
    // a script that arrives in a swapped page does not run by itself (the gallery has one): put in a fresh copy
    document.querySelectorAll("main script").forEach(function (old) {
      var fresh = document.createElement("script");
      fresh.textContent = old.textContent;
      old.replaceWith(fresh);
    });
    document.dispatchEvent(new Event("sheet:swap"));
    var main = document.querySelector("main");
    main.setAttribute("tabindex", "-1");
    main.focus({ preventScroll: true });
    var anchor = u.hash && document.getElementById(decodeURIComponent(u.hash.slice(1)));
    if (anchor) anchor.scrollIntoView();
    else window.scrollTo(0, how === "pop" ? (history.state && history.state.y) || 0 : 0);
  }
  function go(u, how) {
    var mine = ++turn;
    load(u).then(function (page) {
      if (mine !== turn) return; // a newer click has taken over
      var dest = new URL(page.url, location.href), next = parse(page.html);
      if (!next) { location.assign(dest.href); return; }
      apply(next, dest, how);
    }).catch(function () { if (mine === turn) location.assign(u.href); });
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var u = target(e.target.closest && e.target.closest("a"));
    if (!u) return;
    if (u.pathname + u.search === current) {
      // the page you are on: back to the top without a reload. an anchor on it is left to the browser
      if (!u.hash) { e.preventDefault(); window.scrollTo(0, 0); }
      return;
    }
    e.preventDefault();
    go(u, "push");
  });
  window.addEventListener("popstate", function () {
    if (location.pathname + location.search !== current) go(new URL(location.href), "pop");
  });

  function warm(e) {
    var u = target(e.target.closest && e.target.closest("a"));
    if (!u || u.pathname + u.search === current) return;
    clearTimeout(timer);
    timer = setTimeout(function () { load(u).catch(function () {}); }, e.type === "mouseover" ? 60 : 0);
  }
  ["mouseover", "touchstart", "focusin"].forEach(function (n) { document.addEventListener(n, warm, { passive: true }); });

  var conn = window.navigator && window.navigator.connection;
  function later(f) { (window.requestIdleCallback || function (g) { setTimeout(g, 1500); })(f, { timeout: 4000 }); }
  if (!(conn && conn.saveData)) addEventListener("load", function () { setTimeout(function () { later(function () {
      document.querySelectorAll("header a, .links-line a").forEach(function (a) {
        var u = target(a);
        if (u && u.pathname + u.search !== current) load(u).catch(function () {});
      });
    }); }, 1200); }, { once: true });
})();"""

SITE_OG = "/assets/share/site.jpg"
DEFAULT_OG = SITE_OG
WORDS_PER_MINUTE = 225


def frontmatter(text):
    head, body = text.split("\n---\n", 1)
    meta = {}
    for line in head.removeprefix("---\n").splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body.strip()


class Post:
    def __init__(self, path):
        meta, body = frontmatter(path.read_text(encoding="utf-8"))
        self.slug = path.stem
        self.title = meta["title"]
        self.date = datetime.date.fromisoformat(meta["date"])
        self.description = meta["description"]
        self.tags = [t.strip().lower() for t in meta.get("tags", "").split(",") if t.strip()]
        self.cover = meta.get("cover", "")
        self.url = f"/posts/{self.slug}/"
        self.og = f"/assets/og/{self.slug}.png"
        # the picture a link to this post unfurls into: its own cover, unless og_cards makes a card for it
        self.share = self.cover or self.og
        self.minutes = max(1, round(len(body.split()) / WORDS_PER_MINUTE))
        self.standfirst, self.html = render(body)

    @property
    def pretty_date(self):
        return self.date.strftime("%d %b, %Y").lower()


def inline(text):
    """Renders a snippet of markdown without its wrapping paragraph."""
    out = markdown.markdown(text)
    return re.sub(r"^<p>|</p>$", "", out.strip())


LEADING_QUOTE = re.compile(r"\A((?:>.*\n?)+)\n*")


def raster_size(path):
    """(width, height) from the header of a png, jpeg or webp, with no image library"""
    with open(path, "rb") as fh:
        head = fh.read(65536)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        kind = head[12:16]
        if kind == b"VP8X":
            return 1 + int.from_bytes(head[24:27], "little"), 1 + int.from_bytes(head[27:30], "little")
        if kind == b"VP8L":
            b = head[21:25]
            return 1 + (((b[1] & 0x3F) << 8) | b[0]), 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
        if kind == b"VP8 ":
            return int.from_bytes(head[26:28], "little") & 0x3FFF, int.from_bytes(head[28:30], "little") & 0x3FFF
    if head[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(head):
            if head[i] != 0xFF:
                i += 1
                continue
            marker = head[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return int.from_bytes(head[i + 7:i + 9], "big"), int.from_bytes(head[i + 5:i + 7], "big")
            i += 2 + int.from_bytes(head[i + 2:i + 4], "big")
    return None


def svg_size(src):
    """width and height of an image, so the page keeps the room for it while it loads"""
    path = ROOT / src.lstrip("/")
    if not path.is_file():
        return ""
    if src.endswith(".svg"):
        m = re.search(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+) ([\d.]+)"', path.read_text(encoding="utf-8")[:2000])
        if m:
            return f' width="{round(float(m.group(1)))}" height="{round(float(m.group(2)))}"'
        return ""
    dims = raster_size(path)
    if dims and all(dims):
        return f' width="{dims[0]}" height="{dims[1]}"'
    return ""


def figure(m):
    alt, src = m.group(1), m.group(2)
    caption = f"<figcaption>{alt}</figcaption>" if alt.strip() else ""
    img = f'<img src="{src}" alt="{alt}"{svg_size(src)} loading="lazy" decoding="async">'
    webp = re.sub(r"\.(png|jpe?g)$", ".webp", src)
    if webp != src and (ROOT / webp.lstrip("/")).exists():
        img = f'<picture><source type="image/webp" srcset="{webp}">{img}</picture>'
    return f'<figure>{img}{caption}</figure>'


def render(body):
    standfirst = None
    quote = LEADING_QUOTE.match(body)
    if quote:
        lines = [line.removeprefix(">").strip() for line in quote.group(1).splitlines()]
        standfirst = inline(" ".join(lines))
        body = body[quote.end():]

    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists", "attr_list", "toc", "codehilite"],
        extension_configs={
            "toc": {"toc_depth": "2-3"},
            "codehilite": {"css_class": "hl", "guess_lang": False},
        },
    )
    out = md.convert(body)
    out = re.sub(r'<p><img alt="([^"]*)" src="([^"]*)" ?/></p>', figure, out)
    out = out.replace('<div class="hl"><pre>', '<div class="hl"><button class="copy" type="button" aria-label="copy this code">copy</button><pre>')
    out = re.sub(r"(<table>.*?</table>)", r'<div class="table-wrap">\1</div>', out, flags=re.S)
    return standfirst, out


def esc(text):
    return html.escape(text, quote=True)




GITHUB = "https://github.com/Cintu07"
EMAIL = "pawankalyan1892@gmail.com"
JA = "パワン"   # pawan in katakana; the first sound, パ, is the mark in the corner

SOCIALS = [
    ("x", "https://x.com/pawankalyandev"),
    ("linkedin", "https://www.linkedin.com/in/pavankalyan-kolagani/"),
    ("email", "mailto:pawankalyan1892@gmail.com"),
]


def nav_items():
    items = [("/", "writing"), ("/papers/", "papers")]
    if books():
        items.append(("/books/", "books"))
    items.append(("/gallery/", "gallery"))
    return items


def books():
    return json.loads((CONTENT / "books.json").read_text(encoding="utf-8"))


def papers():
    return json.loads((CONTENT / "papers.json").read_text(encoding="utf-8"))


def favourites():
    path = CONTENT / "favourites.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


# ---------------------------------------------------------------- music

MUSIC_DIR = ROOT / "assets" / "music"
AUDIO_TYPES = (".mp3", ".m4a", ".ogg", ".opus", ".wav")

# A code block has a copy button in its corner. The click is handled once, on the document, so it keeps
# working after a page swap replaces the markup. Without a clipboard (an old browser, a plain http page)
# the text is selected in a hidden box and copied the old way.
COPY_JS = r"""(function () {
  document.documentElement.classList.add("can-copy");
  function fallback(text) {
    var t = document.createElement("textarea");
    t.value = text;
    t.setAttribute("readonly", "");
    t.style.position = "fixed";
    t.style.opacity = "0";
    document.body.appendChild(t);
    t.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(t);
    return ok;
  }
  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return fallback(text); });
    }
    return Promise.resolve(fallback(text));
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("button.copy");
    if (!b) return;
    var pre = b.parentNode.querySelector("pre");
    if (!pre) return;
    copy(pre.textContent.replace(/\n$/, "")).then(function (ok) {
      b.textContent = ok ? "copied" : "press ctrl c";
      b.classList.add("done");
      clearTimeout(b._t);
      b._t = setTimeout(function () { b.textContent = "copy"; b.classList.remove("done"); }, 1600);
    });
  });
})();"""

# The song starts by itself when a page opens. A browser will not play sound before the visitor has touched
# the page, so when it refuses the song is started muted, which is always allowed, and the first tap, click or
# key press anywhere turns the sound on. It plays until someone pauses it, and a pause stays a pause. The
# choice and the place in the song survive a reload. Nothing here runs without a track.
MUSIC_JS = """(function () {
function boot() {
  var audio = document.getElementById("music-audio"), btn = document.getElementById("music");
  if (!audio || !btn) return;
  var KEY = "pawan-music", st = { on: true, t: 0 };
  try { st = Object.assign(st, JSON.parse(localStorage.getItem(KEY)) || {}); } catch (e) {}
  function persist() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
  var silent = false; // running, but muted, because the browser has not allowed sound yet
  function paint(playing) {
    btn.classList.toggle("playing", playing);
    btn.classList.toggle("silent", playing && silent);
    btn.setAttribute("aria-pressed", playing ? "true" : "false");
    btn.setAttribute("aria-label", silent ? "turn the sound on" : playing ? "pause music" : "play music");
  }
  // the inputs a browser counts as a touch. a scroll or a hover is not one, and neither is the start of a touch
  var triggers = ["pointerdown", "mousedown", "touchend", "keydown", "click"];
  function arm() { triggers.forEach(function (n) { document.addEventListener(n, onTouch, { passive: true }); }); }
  function disarm() { triggers.forEach(function (n) { document.removeEventListener(n, onTouch); }); }
  function sound() { // the song is already going, so a tap only has to give it its sound
    silent = false;
    audio.muted = false;
    if (audio.paused) { paint(false); return; } // the browser stopped it as it was unmuted: leave it for the next tap
    disarm();
    paint(true);
  }
  function onTouch(e) {
    if (btn.contains(e.target) || !st.on) return;
    if (silent) sound(); else start();
  }
  function start() {
    silent = false;
    audio.muted = false;
    var p = audio.play();
    if (p && p.then) p.then(function () { paint(true); disarm(); }, function () {
      // no sound until the page has been touched. a muted song is allowed, so run it that way and wait for the touch
      audio.muted = true;
      var q = audio.play();
      if (q && q.then) q.then(function () { silent = true; paint(true); }, function () { silent = false; paint(false); });
    });
  }
  audio.volume = 0.35;
  audio.addEventListener("loadedmetadata", function () {
    if (st.t > 0 && st.t < audio.duration - 1) audio.currentTime = st.t;
  }, { once: true });
  audio.addEventListener("error", function () { btn.hidden = true; });
  // if the browser pauses it anyway, say so, and try again at the next touch
  audio.addEventListener("pause", function () { silent = false; paint(false); if (st.on) arm(); });
  var last = 0;
  audio.addEventListener("timeupdate", function () {
    var now = Date.now();
    if (now - last > 1000) { last = now; st.t = audio.currentTime; persist(); }
  });
  window.addEventListener("pagehide", function () { st.t = audio.currentTime; persist(); });
  btn.addEventListener("click", function () {
    if (silent) { st.on = true; persist(); sound(); }
    else if (audio.paused) { st.on = true; persist(); start(); }
    else { st.on = false; persist(); audio.pause(); paint(false); }
  });
  btn.hidden = false;
  paint(false);
  if (st.on) { start(); arm(); }
}
// a page the browser prerendered on hover has not been opened yet: wait, so the song is not
// restarted from a stale position the moment it is opened
function soon() { if (document.readyState === "complete") setTimeout(boot, 600); else addEventListener("load", function () { setTimeout(boot, 600); }, { once: true }); }
if (document.prerendering) document.addEventListener("prerenderingchange", soon, { once: true }); else soon();
})();"""


def music_track():
    """a track in assets/music turns the player on. without one a page has no player at all."""
    tracks = sorted(p for p in MUSIC_DIR.glob("*") if p.suffix.lower() in AUDIO_TYPES) if MUSIC_DIR.is_dir() else []
    return "/assets/music/" + urllib.parse.quote(tracks[0].name) if tracks else ""


def player():
    src = music_track()
    if not src:
        return ""
    return f"""<button id="music" class="music" type="button" aria-pressed="false" aria-label="play music" hidden>
<svg class="play" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>
<span class="bars" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
</button>
<audio id="music-audio" src="{src}" preload="metadata" loop></audio>
<script>{MUSIC_JS}</script>
"""


# ---------------------------------------------------------------- theme and art

# Runs in the head, before anything is drawn, so a page never flashes the wrong theme. A choice made with the
# button is remembered; until there is one the page follows the device, even while it is open. The button
# lives in the header, which a page change replaces, so the click is caught at the document.
THEME_JS = r"""(function () {
  var KEY = "pawan-theme", root = document.documentElement, system = matchMedia("(prefers-color-scheme: dark)");
  function chosen() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function paint(dark) {
    root.setAttribute("data-theme", dark ? "dark" : "light");
    var bar = document.getElementById("theme-color");
    if (bar) bar.setAttribute("content", dark ? "#0f0e0c" : "#cdc5b3");
  }
  var saved = chosen();
  paint(saved ? saved === "dark" : system.matches);
  document.addEventListener("click", function (e) {
    var button = e.target.closest && e.target.closest(".theme");
    if (!button) return;
    var dark = root.getAttribute("data-theme") !== "dark";
    root.classList.add("theme-fade");
    paint(dark);
    setTimeout(function () { root.classList.remove("theme-fade"); }, 380);
    try { localStorage.setItem(KEY, dark ? "dark" : "light"); } catch (err) {}
  });
  if (system.addEventListener) system.addEventListener("change", function (e) { if (!chosen()) paint(e.matches); });
})();"""

THEME_BUTTON = (
    '<button class="theme" type="button" aria-label="switch between day and night">'
    '<span class="night">night</span><span class="day">day</span></button>'
)

# the cutouts tools/cutout.py made, with their sizes and whether each is black ink on transparency
# (ink is drawn white on a dark page, a coloured picture is left as it is)
ART = json.loads((ROOT / "assets" / "art" / "manifest.json").read_text(encoding="utf-8")) if (ROOT / "assets" / "art" / "manifest.json").exists() else {}


GALLERY_DIR = ROOT / "assets" / "gallery"


def gallery():
    path = CONTENT / "gallery.json"
    if not path.exists() or not (GALLERY_DIR / "manifest.json").exists():
        return []
    sizes = json.loads((GALLERY_DIR / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for e in json.loads(path.read_text(encoding="utf-8")):
        name = re.sub(r"[^a-z0-9]+", "-", e["title"].lower()).strip("-")
        if name in sizes:
            out.append({**e, "name": name, **sizes[name]})
    return out


# the tv changes channel every few seconds, and on a click; the wall opens a picture full size.
# arrows step through them, escape closes. without script the pictures are still links to the files.
GALLERY_JS = r"""(function () {
  function boot() {
    var screen = document.querySelector(".tv .screen img"), tv = document.querySelector(".tv");
    var items = [].slice.call(document.querySelectorAll(".wall a"));
    if (screen && items.length) {
      var ch = 0, timer;
      var tune = function () { ch = (ch + 1) % items.length; screen.src = items[ch].querySelector("img").src; screen.alt = items[ch].dataset.title; };
      var run = function () { clearInterval(timer); timer = setInterval(tune, 2600); };
      tv.addEventListener("click", function () { tune(); run(); });
      if (!matchMedia("(prefers-reduced-motion: reduce)").matches) run();
    }
    var dlg = document.querySelector(".viewer");
    if (!dlg || !dlg.showModal) return;
    var img = dlg.querySelector("img"), cap = dlg.querySelector("p"), at = 0;
    var show = function (i) {
      at = (i + items.length) % items.length;
      var a = items[at];
      img.src = a.getAttribute("href"); img.alt = a.dataset.title;
      cap.innerHTML = "";
      cap.appendChild(document.createTextNode(a.dataset.title + " "));
      var meta = document.createElement("span"); meta.textContent = a.dataset.meta; cap.appendChild(meta);
    };
    items.forEach(function (a, i) { a.addEventListener("click", function (e) { e.preventDefault(); show(i); dlg.showModal(); }); });
    dlg.querySelector(".prev").addEventListener("click", function () { show(at - 1); });
    dlg.querySelector(".next").addEventListener("click", function () { show(at + 1); });
    dlg.querySelector(".close").addEventListener("click", function () { dlg.close(); });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
    dlg.addEventListener("keydown", function (e) { if (e.key === "ArrowLeft") show(at - 1); if (e.key === "ArrowRight") show(at + 1); });
  }
  boot();
})();"""


def gallery_page(items):
    if not items:
        return
    figures = []
    for i, g in enumerate(items, 1):
        meta = g["kind"] + (f", {g['by']}" if g["by"] else "")
        by = f'<span class="by">{esc(g["by"])}</span>' if g["by"] else ""
        figures.append(f"""<figure><a href="/assets/gallery/{g["big"]}" data-title="{esc(g["title"])}" data-meta="{esc(meta)}">
<img src="/assets/gallery/{g["name"]}-s.webp" width="{g["sw"]}" height="{g["sh"]}" alt="{esc(g["title"])}" loading="{"eager" if i <= 6 else "lazy"}" decoding="async"></a>
<figcaption><span><span class="n">{i:02d}</span>{esc(g["title"])}{by}</span><span class="k">{esc(g["kind"])}</span></figcaption></figure>""")
    first = items[0]
    body = f"""<main class="gallery">
<section class="intro">
<div>
<h1>gallery</h1>
<p>pictures i saved because i kept looking at them: prints, stamps, pixel art, a few film stills.</p>
<p class="small">none of these are mine. the artist is named where i know it; if one is yours and you want a credit or want it gone, <a href="mailto:{EMAIL}">write to me</a>.</p>
</div>
<figure class="tv" title="change the channel"><div class="set"><img src="/assets/gallery/tv-set.webp" width="486" height="338" alt="an old television">
<div class="screen"><img src="/assets/gallery/{first["name"]}-s.webp" alt="{esc(first["title"])}"></div></div>
<figcaption>{len(items)} channels. click to change</figcaption></figure>
</section>
<div class="wall">
{"".join(figures)}
</div>
<dialog class="viewer" aria-label="picture"><button class="close" type="button" aria-label="close">&#215;</button><button class="prev" type="button" aria-label="previous">&#8592;</button><img alt=""><button class="next" type="button" aria-label="next">&#8594;</button><p></p></dialog>
<script>{GALLERY_JS}</script>
</main>"""
    write("/gallery/", layout(title="gallery", description="pictures i saved: prints, stamps, pixel art.", path="/gallery/", body=body, nav="/gallery/", share_title="gallery"))


SHEET_JS = r"""(function () {
  var still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function boot() {
    var home = document.querySelector("main.home"), first = false;
    try { first = !sessionStorage.getItem("pawan-typed"); sessionStorage.setItem("pawan-typed", "1"); } catch (e) {}
    if (home && first && !still) {
      var words = home.querySelector(".lede .words");
      if (words) {
        var text = words.textContent, i = 0;
        words.textContent = "";
        (function type() { i += 2; words.textContent = text.slice(0, i); if (i < text.length) setTimeout(type, 15); })();
      }
    }
  }
  function books() {
    if (still || !matchMedia("(hover: none)").matches || !("IntersectionObserver" in window)) return;
    var io = new IntersectionObserver(function (seen) {
      seen.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        e.target.classList.add("open");
        setTimeout(function () { e.target.classList.remove("open"); }, 2600);
      });
    }, { threshold: 0.8 });
    document.querySelectorAll(".tome").forEach(function (t) { io.observe(t); });
  }
  boot(); books();
  document.addEventListener("sheet:swap", function () { boot(); books(); });
})();"""


def print_art(name, cls, label=""):
    role = f' role="img" aria-label="{esc(label)}"' if label else ' aria-hidden="true"'
    return f'<div class="print {cls}" style="--art:url(/assets/print/{name}.png)"{role}></div>'


def art(name, eager=False):
    a = ART.get(name)
    if not a:
        return ""
    classes = f'art {name}' + (" ink" if a["ink"] else "")
    loading = ' fetchpriority="high"' if eager else ' loading="lazy"'
    return f'<img class="{classes}" src="/assets/art/{name}.webp" width="{a["w"]}" height="{a["h"]}" alt=""{loading} decoding="async">'


def minify_css(css):
    """comments out, whitespace collapsed, no space around { } ; , : where css never needs it"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,])\s*", r"\1", css)
    css = re.sub(r";}", "}", css)
    return css.strip()


SITE_CSS = None


def site_css():
    global SITE_CSS
    if SITE_CSS is None:
        SITE_CSS = minify_css((ROOT / "assets" / "site.css").read_text(encoding="utf-8"))
    return SITE_CSS


def minify_js(js):
    """only what is safe without a parser: comment lines and leading indentation"""
    lines = [line.strip() for line in js.splitlines()]
    return "\n".join(line for line in lines if line and not line.startswith("//"))


def layout(*, title, description, path, body, nav, og_image=DEFAULT_OG, article=None, chrome=True, share_title=None, folio="1 / 1"):
    full_title = NAME if path == "/" else f"{title} · {NAME}"
    canonical = SITE + path
    og = og_image if og_image.startswith("http") else SITE + og_image
    ld = {
        "@context": "https://schema.org",
        "@type": "BlogPosting" if article else "WebSite",
        "headline" if article else "name": title if article else NAME,
        "description": description,
        "url": canonical,
        "author": {"@type": "Person", "name": "Pawan Kalyan", "url": "https://pawann.dev"},
    }
    if article:
        ld["datePublished"] = article.date.isoformat()
        ld["image"] = og
    links = "".join(
        '<a href="{}"{}>{}</a>'.format(href, ' aria-current="page"' if href == nav else "", label)
        for href, label in nav_items()
    )
    music = player()
    socials = "".join(f'<a href="{href}"{"" if href.startswith("mailto:") else " rel=\"me noreferrer\""}>{label}</a>' for label, href in SOCIALS)
    header_html = f"""<header>
<a class="home" href="/"><span class="ja" lang="ja">{JA[0]}</span>pawan.2026</a>
<nav>{links}{THEME_BUTTON}</nav>
<div class="ribbon" aria-hidden="true"></div>
</header>
""" if chrome else ""
    cc = " ".join([f'<a href="{href}" rel="me noreferrer">{label}</a>' for label, href in SOCIALS if not href.startswith("mailto:")]
                  + [f'<a href="{GITHUB}" rel="me noreferrer">github</a>', '<a href="https://pawann.dev">pawann.dev</a>', '<a href="/feed.xml">rss</a>'])
    footer_html = f"""<footer>
<div class="signoff">
<div>
<dl>
<dt>cc:</dt><dd>{cc}</dd>
<dt>to:</dt><dd><a href="mailto:{EMAIL}">{EMAIL}</a></dd>
<dt>enc:</dt><dd><a href="/archive/">the window version, nov 2026</a></dd>
</dl>
<p class="yours">yours,<b>pawan kalyan</b></p>
</div>
</div>
<p class="closing"><span>old memory of new time ....</span><span>{folio}</span></p>
</footer>
""" if chrome else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="darkreader-lock">
<meta name="theme-color" id="theme-color" content="#cdc5b3">
<script>{minify_js(THEME_JS)}</script>
<title>{esc(full_title.lower())}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical}">
<link rel="alternate" type="application/rss+xml" title="{NAME}" href="/feed.xml">
<link rel="icon" href="/assets/img/icon.png">
<meta property="og:site_name" content="{NAME}">
<meta property="og:type" content="{"article" if article else "website"}">
<meta property="og:title" content="{esc((share_title or (title if article else NAME)).lower())}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{og}">
<style>{site_css()}</style>
<script type="application/ld+json">{json.dumps(ld)}</script>
</head>
<body{' class="has-music"' if music else ''}>
{header_html}{body}
{footer_html}{music}<script>{minify_js(COPY_JS + NAV_JS + SHEET_JS)}</script>
</body>
</html>
"""


def write(path, text):
    target = DIST / path.lstrip("/")
    if target.suffix == "":
        target = target / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- books

def size_of(path):
    n = (ROOT / path.lstrip("/")).stat().st_size
    return f"{n / 1_000_000:.1f} mb" if n >= 1_000_000 else f"{round(n / 1000)} kb"


def wide_cover(page, dest):
    """the top of the first page, cut to 16:9 and 1200 wide. it starts a little above the first thing
    printed on the page, which is where a title is"""
    import pymupdf

    probe = page.get_pixmap(dpi=36)
    first = 0
    for y in range(probe.height):
        if min(probe.samples[y * probe.stride:(y + 1) * probe.stride]) < 225:
            first = y
            break
    width, tall = page.rect.width, page.rect.height
    height = width * 9 / 16
    top = min(max(0.0, first * width / probe.width - 0.05 * tall), max(0.0, tall - height))
    k = 1200 / width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(k, k), clip=pymupdf.Rect(0, top, width, top + height))
    pix.save(dest, jpg_quality=84)
    return pix.width, pix.height


def book_slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "book"


def og_book_card(b, page):
    """the picture a link to a book's page unfurls into: its title on the left and its cover standing on the right.
    a pdf has nowhere to put a preview, which is why a link to the file itself shows nothing"""
    import pymupdf

    virgil = pymupdf.Font(fontfile=str(OG_DIR / "virgil.ttf"))
    doc = pymupdf.open()
    card = doc.new_page(width=1200, height=630)
    card.draw_rect(card.rect, color=None, fill=(1, 1, 1))

    top, bottom = 62, 568
    scale = (bottom - top) / page.rect.height
    cover = page.get_pixmap(matrix=pymupdf.Matrix(scale * 2, scale * 2))
    right = 1200 - 88
    left = right - page.rect.width * scale
    for i, opacity in enumerate((0.06, 0.04, 0.025)):  # a soft shadow, as a few faint rectangles
        card.draw_rect(pymupdf.Rect(left + 3 + i * 3, top + 8 + i * 3, right + 3 + i * 3, bottom + 8 + i * 3), color=None, fill=(0, 0, 0), fill_opacity=opacity)
    card.insert_image(pymupdf.Rect(left, top, right, bottom), pixmap=cover)
    card.draw_rect(pymupdf.Rect(left, top, right, bottom), color=(0.82, 0.84, 0.87), width=1)

    room = left - 84 - 56
    size = 76
    lines = wrap(virgil, b["title"].lower(), size, room)
    while (len(lines) > 3 or any(virgil.text_length(line, fontsize=size) > room for line in lines)) and size > 40:
        size -= 4
        lines = wrap(virgil, b["title"].lower(), size, room)
    leading = size * 1.1
    y = 215
    title, soft, blue = pymupdf.TextWriter(card.rect), pymupdf.TextWriter(card.rect), pymupdf.TextWriter(card.rect)
    blue.append((86, 118), f"{NAME}  ·  book", font=virgil, fontsize=28)
    for line in lines:
        title.append((84, y), line, font=virgil, fontsize=size)
        y += leading
    for line in wrap(virgil, b.get("subtitle", "").lower(), 27, room)[:3]:
        soft.append((86, y + 18), line, font=virgil, fontsize=27)
        y += 36
    meta = " · ".join(x for x in (f'{b["pages"]} pages' if b.get("pages") else "", "free pdf") if x)
    soft.append((86, 548), meta, font=virgil, fontsize=26)
    title.write_text(card, color=INK)
    soft.write_text(card, color=FAINT)
    blue.write_text(card, color=BLUE)

    target = DIST / "assets" / "og" / f"book-{b['slug']}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    card.get_pixmap(dpi=72).save(target)


def prepare_book(b):
    """books uploaded from the sandbox come with only a pdf. the cover is its
    first page and the page count is read off the file."""
    pdf = b.get("pdf")
    if not pdf:
        return b
    import pymupdf

    doc = pymupdf.open(ROOT / pdf.lstrip("/"))
    b = {**b, "pages": b.get("pages") or len(doc)}
    if not b.get("cover"):
        name = Path(pdf).stem + "-cover.jpg"
        target = DIST / "assets" / "books" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        pix = doc[0].get_pixmap(dpi=100)
        pix.save(target, jpg_quality=86)
        b["cover"] = f"/assets/books/{name}"
        b["cover_size"] = (pix.width, pix.height)
    # the banner is cut from the first page whether or not the book brought a cover of its own
    wide = Path(pdf).stem + "-wide.jpg"
    (DIST / "assets" / "books").mkdir(parents=True, exist_ok=True)
    w, h = wide_cover(doc[0], DIST / "assets" / "books" / wide)
    b["cover_wide"] = (f"/assets/books/{wide}", w, h)
    b["slug"] = book_slug(b["title"])
    b["url"] = f"/books/{b['slug']}/"
    b["share"] = f"/assets/og/book-{b['slug']}.png"
    og_book_card(b, doc[0])
    return b


def tome(b, big=False):
    """a book you can open: cover, spine, page edges and a back, in 3d. hovering (or, on a touch
    screen, scrolling it into view) swings the cover open and flips three pages to the title page"""
    if not b.get("cover"):
        return ""
    src = b["cover"]
    webp = re.sub(r"\.(png|jpe?g)$", ".webp", src)
    if webp != src and (ROOT / webp.lstrip("/")).exists():
        src = webp
    href = b["pdf"] if big else b.get("url", b["pdf"])
    pages = f'{b["pages"]} pages' if b.get("pages") else ""
    return f"""<a class="tome{" big" if big else ""}" href="{href}"{" download" if big else ""} aria-label="{"download" if big else "open"} {esc(b["title"])}">
<span class="tome-body" aria-hidden="true">
<span class="tome-back"></span><span class="tome-edge"></span><span class="tome-spine"><i>{esc(b["title"])}</i></span>
<span class="tome-leaf"><b>{esc(b["title"])}</b><em>pawan kalyan</em><small>{pages}</small></span>
<span class="tome-page p3"></span><span class="tome-page p2"></span><span class="tome-page p1"></span>
<span class="tome-cover"><img src="{src}" alt="" loading="lazy" decoding="async"><span class="inside"></span></span>
</span>
</a>"""


def book_card(b, big=False, heading="h3"):
    meta = " · ".join(x for x in (b.get("year", ""), f'{b["pages"]} pages' if b.get("pages") else "", "free pdf") if x)
    code = f'<a class="code-link" href="{b["code"]}" download>source code <span>{size_of(b["code"])}</span></a>' if b.get("code") else ""
    blurb = f'<p class="note">{esc(b["blurb"])}</p>' if big and b.get("blurb") else ""
    subtitle = f'<p class="subtitle">{esc(b["subtitle"])}</p>' if b.get("subtitle") else ""
    title = f'<a href="{b["url"]}">{esc(b["title"])}</a>' if b.get("url") and heading != "h1" else esc(b["title"])
    return f"""<div class="book{" big" if big else ""}">
{tome(b, big)}
<div>
<{heading}>{title}</{heading}>
{subtitle}
{blurb}
<p class="meta">{esc(meta)}</p>
<div class="actions"><a class="button" href="{b["pdf"]}" download>download the pdf <span>{size_of(b["pdf"])}</span></a>{code}</div>
</div>
</div>"""


def books_page(entries):
    if not entries:
        return
    body = f"""<main class="page">
<h1>books i write</h1>
<p class="lede-small">free to download, all of them.</p>

{"".join(book_card(b, big=True) for b in entries)}
</main>"""
    write("/books/", layout(title="books", description=entries[0].get("blurb", ""), path="/books/", body=body, nav="/books/",
                            og_image=entries[0].get("share", entries[0].get("cover", DEFAULT_OG)), share_title="books"))


def book_page(b):
    """the page to share: a link to the pdf itself has no preview, a link to this one has the card"""
    body = f"""<main class="page">
<p class="back"><a href="/books/">all books</a></p>
{book_card(b, big=True, heading="h1")}
</main>"""
    write(b["url"], layout(title=b["title"], description=b.get("subtitle") or b.get("blurb", ""), path=b["url"], body=body, nav="/books/",
                           og_image=b.get("share", DEFAULT_OG), share_title=b["title"]))


# ---------------------------------------------------------------- link previews

OG_DIR = ROOT / "og"
INK = (30 / 255, 30 / 255, 30 / 255)
FAINT = (108 / 255, 115 / 255, 122 / 255)
BLUE = (25 / 255, 113 / 255, 194 / 255)


def wrap(font, text, size, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and font.text_length(trial, fontsize=size) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines


def og_card(target, *, title, kicker="", footer="", title_size=(64, 36), max_lines=4):
    """the 1200x630 picture a link unfurls into on x, linkedin, slack and imessage.
    virgil on white, the pagoda faded in on the right."""
    import pymupdf

    roman = pymupdf.Font(fontfile=str(OG_DIR / "virgil.ttf"))
    doc = pymupdf.open()
    page = doc.new_page(width=1200, height=630)
    page.insert_image(page.rect, filename=str(OG_DIR / "background.png"))
    big, small, accent = pymupdf.TextWriter(page.rect), pymupdf.TextWriter(page.rect), pymupdf.TextWriter(page.rect)

    size = title_size[0]
    while (lines := wrap(roman, title, size, 640)) and len(lines) > max_lines and size > title_size[1]:
        size -= 4
    lines = lines[:max_lines]
    leading = size * 1.08
    top = 315 - leading * len(lines) / 2 + size * 0.75
    for i, line in enumerate(lines):
        big.append((84, top + i * leading), line, font=roman, fontsize=size)
    if kicker:
        accent.append((86, 118), kicker, font=roman, fontsize=28)
    if footer:
        small.append((86, 548), footer, font=roman, fontsize=26)
    big.write_text(page, color=INK)
    small.write_text(page, color=FAINT)
    accent.write_text(page, color=BLUE)

    target = DIST / target.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=72).save(target)


def og_wide_cover(post):
    """a cover wider than a share card would lose its edges on x and linkedin, and with them
    the title. a wide one goes onto a card of its own colour instead, so nothing is cut."""
    import pymupdf

    src = ROOT / post.cover.lstrip("/")
    if src.suffix.lower() not in (".jpg", ".jpeg", ".png") or not src.is_file():
        return False
    pix = pymupdf.Pixmap(src)
    if pix.width / pix.height < 2.0:
        return False

    def edge(y):
        """the colour along one edge of the cover, as 0-1 floats"""
        px = [pix.pixel(x, y) for x in range(0, pix.width, max(1, pix.width // 40))]
        return tuple(sum(c[i] for c in px) / len(px) / 255 for i in range(3))

    doc = pymupdf.open()
    page = doc.new_page(width=1200, height=630)
    height = 1200 * pix.height / pix.width
    top = (630 - height) / 2
    page.draw_rect(pymupdf.Rect(0, 0, 1200, 315), color=None, fill=edge(2))
    page.draw_rect(pymupdf.Rect(0, 315, 1200, 630), color=None, fill=edge(pix.height - 3))
    page.insert_image(pymupdf.Rect(0, top, 1200, top + height), filename=str(src))

    target = DIST / post.og.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=72).save(target)
    return True


def og_cards(posts):
    # the share cards are typed sheets, photographed once (assets/share). a post without one gets the old card
    for p in posts:
        card = f"/assets/share/post-{p.slug}.jpg"
        if (ROOT / card.lstrip("/")).exists():
            p.share = card
            continue
        if p.cover and og_wide_cover(p):
            p.share = p.og
            continue
        og_card(p.og, title=p.title.lower(), kicker=f"{NAME}  ·  writing",
                footer=f"{SITE.removeprefix('https://')}  ·  {p.minutes} min read  ·  {p.pretty_date}")


# ---------------------------------------------------------------- pages

def tag_of(post):
    return post.tags[0].lower() if post.tags else "writing"


def index_row(url, number, title, right):
    return (f'<li><a href="{url}"><span class="no">{number}</span><span class="t">{esc(title)}</span>'
            f'<span class="dots"></span><span class="dt">{right}</span></a></li>\n')


def home(posts, entries):
    n = len(posts)
    rows = "".join(index_row(p.url, f"{n - i:02d}.", p.title, p.date.strftime("%d.%m.%y")) for i, p in enumerate(posts))
    paper_rows = "".join(index_row(p["url"], f"p{i}.", p["title"], esc(p["codeName"])) for i, p in enumerate(papers(), 1))
    fav_rows = "".join(index_row(p["url"], f"f{i}.", p["title"], esc(p["venue"].rsplit(", ", 1)[-1])) for i, p in enumerate(favourites(), 1))
    fav_html = f"""<section>
<h2 class="label"><a href="/papers/#favourites">papers i love</a> <span>{len(favourites())}</span></h2>
<ul class="rows">
{fav_rows}</ul>
</section>""" if fav_rows else ""
    books_html = f"""<section id="books">
<h2 class="label"><a href="/books/">books, free</a> <span>{len(entries)}</span></h2>
{"".join(book_card(b) for b in entries)}
</section>""" if entries else ""
    pics = gallery()
    strip_html = ""
    if pics:
        cells = "".join(f'<li><a href="/gallery/" title="{esc(g["title"])}"><img src="/assets/gallery/{g["name"]}-t.webp" width="240" height="240" alt="{esc(g["title"])}" loading="lazy" decoding="async"></a></li>' for g in pics[:6])
        strip_html = f"""<section id="gallery">
<h2 class="label"><a href="/gallery/">pinned to the sheet</a> <span>{len(pics)} in the gallery</span></h2>
<ul class="strip">{cells}</ul>
</section>"""
    since = min(p.date for p in posts).strftime("%b %Y").lower()
    elsewhere = '<span class="sep">,</span> '.join(
        [f'<a href="{href}" rel="me noreferrer">{label}</a>' for label, href in SOCIALS if not href.startswith("mailto:")]
        + [f'<a href="{GITHUB}" rel="me noreferrer">github</a>', '<a href="https://pawann.dev">pawann.dev</a>'])
    body = f"""<main class="home">
<h1 class="title">pawan kalyan<span class="ja" lang="ja">{JA}</span></h1>
<p class="lede"><span class="words">i'm pawan. i build database and inference stuff and break it a lot. this is where i write down why.</span><span class="caret" aria-hidden="true"></span></p>
<dl class="facts">
<dt>good at</dt><dd>{GOOD_AT}</dd>
<dt>languages</dt><dd>{LANGUAGES}</dd>
<dt>elsewhere</dt><dd>{elsewhere}</dd>
</dl>
<section id="writing">
<h2 class="label">writing <span>{n} sheets</span></h2>
<ul class="rows">
{rows}</ul>
</section>
{strip_html}
{books_html}
<section id="papers">
<h2 class="label"><a href="/papers/">papers i implement</a> <span>{len(papers())}</span></h2>
<ul class="rows">
{paper_rows}</ul>
</section>
{fav_html}
</main>"""
    write("/index.html", layout(title=NAME, description=TAGLINE, path="/", body=body, nav="/"))


def article(post, posts):
    standfirst = f'<div class="standfirst"><p>{post.standfirst}</p></div>' if post.standfirst else ""
    tags = f'<p class="tags">filed under: {esc(", ".join(t.lower() for t in post.tags))}</p>' if post.tags else ""
    oldest_first = sorted(posts, key=lambda p: p.date)
    number, n = oldest_first.index(post) + 1, len(posts)
    others = [p for p in posts if p is not post][:5]
    more = ""
    if others:
        links = "".join(index_row(p.url, f"{oldest_first.index(p) + 1:02d}.", p.title, p.date.strftime("%d.%m.%y")) for p in others)
        more = f'<section class="more"><h2 class="label">more sheets</h2><ul class="rows">{links}</ul></section>'
    body = f"""<main class="post">
<p class="folio"><span>sheet {number:02d} of {n:02d}</span><span>{esc(tag_of(post))}</span></p>
<h1>{esc(post.title)}</h1>
<p class="byline"><span><time datetime="{post.date.isoformat()}">{post.pretty_date}</time></span><span>{post.minutes} min read</span></p>
{standfirst}
<article class="prose">
{post.html}
</article>
<p class="endmark" aria-label="the end">- 30 -</p>
{tags}
{more}
</main>"""
    write(post.url, layout(
        title=post.title, description=post.description, path=post.url, body=body, nav="/",
        og_image=post.share, article=post, folio=f"{number:02d} / {n:02d}",
    ))


def papers_page():
    items = []
    for p in papers():
        items.append(f"""<div class="item">
<h2><a href="{p["url"]}">{esc(p["title"])}</a></h2>
<p class="by">{esc(p["authors"])}, {esc(p["venue"])}</p>
<p class="note">{esc(p["note"])}</p>
<p class="links"><a href="{p["url"]}">the paper</a><a href="{p["code"]}">{esc(p["codeName"])}, the code</a></p>
</div>""")
    loved = []
    for p in favourites():
        loved.append(f"""<div class="item">
<h2><a href="{p["url"]}">{esc(p["title"])}</a></h2>
<p class="by">{esc(p["authors"])}, {esc(p["venue"])}</p>
<p class="note">{esc(p["note"])}</p>
</div>""")
    fav_html = ""
    if loved:
        fav_html = f"""<h1 id="favourites" class="second">papers i love</h1>
<p class="lede-small">not mine, just the ones i keep going back to.</p>
{"".join(loved)}"""
    body = f"""<main class="page">
<h1>papers i implement</h1>
<p class="lede-small">the ones i read with an editor open. each links to the code.</p>
{"".join(items)}
{fav_html}
</main>"""
    write("/papers/", layout(title="papers", description="research papers i implement, with the code.", path="/papers/", body=body, nav="/papers/", share_title="papers"))


def not_found():
    body = f"""<main class="notfound"><h1>404</h1><p>nothing typed on this sheet yet. <a href="/">back to the index</a>.</p></main>"""
    write("/404.html", layout(title="not found", description="page not found.", path="/404.html", body=body, nav="", chrome=False))


def feed(posts):
    items = "".join(f"""<item>
<title>{esc(p.title)}</title>
<link>{SITE}{p.url}</link>
<guid>{SITE}{p.url}</guid>
<pubDate>{email.utils.format_datetime(datetime.datetime.combine(p.date, datetime.time(), datetime.timezone.utc))}</pubDate>
<description>{esc(p.description)}</description>
</item>
""" for p in posts)
    write("/feed.xml", f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>{NAME}</title>
<link>{SITE}/</link>
<description>{esc(TAGLINE)}</description>
<atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>
{items}</channel>
</rss>
""")


def posts_json(posts):
    """pawann.dev reads its blog from this, so a post published here shows up there too."""
    def absolute(src):
        return SITE + src if src.startswith("/") else src

    out = []
    for p in posts:
        body = frontmatter((CONTENT / "posts" / f"{p.slug}.md").read_text(encoding="utf-8"))[1]
        body = re.sub(r"(!\[[^\]]*\]\()(/[^)\s]+)", lambda m: m.group(1) + absolute(m.group(2)), body)
        out.append({
            "slug": p.slug,
            "title": p.title,
            "date": p.date.isoformat(),
            "description": p.description,
            "tags": p.tags,
            "cover": absolute(p.cover) if p.cover else "",
            "og": absolute(p.share),
            "minutes": p.minutes,
            "url": SITE + p.url,
            "markdown": body,
        })
    write("/posts.json", json.dumps(out, ensure_ascii=False))


NUMBER = re.compile(r"-?\d+\.\d+")


def _short(m):
    s = f"{round(float(m.group()), 2):.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def shrink_svgs():
    """an excalidraw export draws its text as glyph outlines with six decimals each. two decimals draw
    the same picture (checked pixel for pixel at 2x) in about a third less markup. only the copies in
    dist are touched, the files in assets stay exactly as they were exported."""
    for path in (DIST / "assets" / "img").rglob("*.svg"):
        if path.stat().st_size < 20_000:
            continue
        svg = path.read_text(encoding="utf-8")
        svg = re.sub(r'(\sd=")([^"]*)(")', lambda m: m.group(1) + re.sub(r"\s+", " ", NUMBER.sub(_short, m.group(2))).strip() + m.group(3), svg)
        path.write_text(re.sub(r">\s+<", "><", svg), encoding="utf-8", newline="\n")


def sitemap(posts, entries):
    urls = ["/", "/papers/", "/gallery/"] + (["/books/"] + [b["url"] for b in entries if b.get("url")] if entries else []) + [p.url for p in posts]
    body = "".join(f"<url><loc>{SITE}{u}</loc></url>\n" for u in urls)
    write("/sitemap.xml", f'<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n')
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.copytree(ROOT / "assets", DIST / "assets")
    # the window version of the site (nov 2026), kept as it was at /archive/. it is a finished build, made by
    # tools/make_archive.mjs; files it shares with this site are served from here, not copied twice
    if (ROOT / "archive").is_dir():
        shutil.copytree(ROOT / "archive", DIST / "archive")
    shrink_svgs()
    posts = sorted((Post(p) for p in (CONTENT / "posts").glob("*.md")), key=lambda p: p.date, reverse=True)
    entries = [prepare_book(b) for b in books()]
    og_cards(posts)
    home(posts, entries)
    for post in posts:
        article(post, posts)
    papers_page()
    gallery_page(gallery())
    books_page(entries)
    for b in entries:
        if b.get("url"):
            book_page(b)
    not_found()
    feed(posts)
    posts_json(posts)
    sitemap(posts, entries)
    print(f"built {len(posts)} posts and {len(entries)} books into {DIST.name}/")


if __name__ == "__main__":
    main()
