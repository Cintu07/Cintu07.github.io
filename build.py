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
    if (u.origin !== location.origin || /\.[a-z0-9]+$/i.test(u.pathname)) return null;
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
      var run = function () { apply(next, dest, how); };
      if (document.startViewTransition && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) document.startViewTransition(run);
      else run();
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
  if (!(conn && conn.saveData)) {
    (window.requestIdleCallback || function (f) { setTimeout(f, 1500); })(function () {
      document.querySelectorAll("header nav a").forEach(function (a) {
        var u = target(a);
        if (u && u.pathname + u.search !== current) load(u).catch(function () {});
      });
    });
  }
})();"""

SITE_OG = "/assets/og/site.png"
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


def svg_size(src):
    """width and height from an svg's viewBox, so the page keeps the room for it while it loads"""
    path = ROOT / src.lstrip("/")
    if src.endswith(".svg") and path.is_file():
        m = re.search(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+) ([\d.]+)"', path.read_text(encoding="utf-8")[:2000])
        if m:
            return f' width="{round(float(m.group(1)))}" height="{round(float(m.group(2)))}"'
    return ""


def figure(m):
    alt, src = m.group(1), m.group(2)
    caption = f"<figcaption>{alt}</figcaption>" if alt.strip() else ""
    return f'<figure><img src="{src}" alt="{alt}"{svg_size(src)} loading="lazy" decoding="async">{caption}</figure>'


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
    out = re.sub(r"(<table>.*?</table>)", r'<div class="table-wrap">\1</div>', out, flags=re.S)
    return standfirst, out


def esc(text):
    return html.escape(text, quote=True)




SOCIALS = [
    ("x", "https://x.com/pawankalyandev"),
    ("linkedin", "https://www.linkedin.com/in/pavankalyan-kolagani/"),
    ("email", "mailto:pawankalyan1892@gmail.com"),
]


def nav_items():
    items = [("/", "writing"), ("/papers/", "papers")]
    if books():
        items.append(("/books/", "books"))
    items.append(("https://pawann.dev", "pawann.dev"))
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

# like the main site: the track starts by itself on the first touch, until someone pauses it, and the
# choice and the place in the song follow you from page to page. nothing here runs without a track.
MUSIC_JS = """(function () {
function boot() {
  var audio = document.getElementById("music-audio"), btn = document.getElementById("music");
  if (!audio || !btn) return;
  var KEY = "pawan-music", st = { on: true, t: 0 };
  try { st = Object.assign(st, JSON.parse(localStorage.getItem(KEY)) || {}); } catch (e) {}
  function persist() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
  function paint(playing) {
    btn.classList.toggle("playing", playing);
    btn.setAttribute("aria-pressed", playing ? "true" : "false");
    btn.setAttribute("aria-label", playing ? "pause music" : "play music");
  }
  var triggers = ["pointerdown", "keydown", "touchend"];
  function arm() { triggers.forEach(function (n) { document.addEventListener(n, onTouch, { passive: true }); }); }
  function disarm() { triggers.forEach(function (n) { document.removeEventListener(n, onTouch); }); }
  function onTouch(e) { if (!btn.contains(e.target) && st.on) start(); }
  function start() {
    var p = audio.play();
    if (p && p.then) p.then(function () { paint(true); disarm(); }, function () { paint(false); });
  }
  audio.volume = 0.35;
  audio.addEventListener("loadedmetadata", function () {
    if (st.t > 0 && st.t < audio.duration - 1) audio.currentTime = st.t;
  }, { once: true });
  audio.addEventListener("error", function () { btn.hidden = true; });
  var last = 0;
  audio.addEventListener("timeupdate", function () {
    var now = Date.now();
    if (now - last > 1000) { last = now; st.t = audio.currentTime; persist(); }
  });
  window.addEventListener("pagehide", function () { st.t = audio.currentTime; persist(); });
  btn.addEventListener("click", function () {
    if (audio.paused) { st.on = true; persist(); start(); }
    else { audio.pause(); st.on = false; persist(); paint(false); }
  });
  btn.hidden = false;
  paint(false);
  if (st.on) { start(); arm(); }
}
// a page the browser prerendered on hover has not been opened yet: wait, so the song is not
// restarted from a stale position the moment it is opened
if (document.prerendering) document.addEventListener("prerenderingchange", boot, { once: true }); else boot();
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
    if (bar) bar.setAttribute("content", dark ? "#101212" : "#ffffff");
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
    '<button class="theme" type="button" aria-label="switch between light and dark">'
    '<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
    '<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
    "</button>"
)

# the cutouts tools/cutout.py made, with their sizes and whether each is black ink on transparency
# (ink is drawn white on a dark page, a coloured picture is left as it is)
ART = json.loads((ROOT / "assets" / "art" / "manifest.json").read_text(encoding="utf-8")) if (ROOT / "assets" / "art" / "manifest.json").exists() else {}


def art(name, eager=False):
    a = ART.get(name)
    if not a:
        return ""
    classes = f'art {name}' + (" ink" if a["ink"] else "")
    loading = ' fetchpriority="high"' if eager else ' loading="lazy"'
    return f'<img class="{classes}" src="/assets/art/{name}.webp" width="{a["w"]}" height="{a["h"]}" alt=""{loading} decoding="async">'


def layout(*, title, description, path, body, nav, og_image=DEFAULT_OG, article=None):
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
    plinth = f'<div class="plinth">{art("frieze")}</div>' if art("frieze") else ""
    socials = "".join(f'<a href="{href}"{"" if href.startswith("mailto:") else " rel=\"me noreferrer\""}>{label}</a>' for label, href in SOCIALS)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="darkreader-lock">
<meta name="theme-color" id="theme-color" content="#ffffff">
<script>{THEME_JS}</script>
<title>{esc(full_title.lower())}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical}">
<link rel="alternate" type="application/rss+xml" title="{NAME}" href="/feed.xml">
<link rel="icon" href="/assets/img/icon.png">
<link rel="preload" href="/assets/fonts/et-book-roman.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/virgil.woff2" as="font" type="font/woff2" crossorigin>
<meta property="og:site_name" content="{NAME}">
<meta property="og:type" content="{"article" if article else "website"}">
<meta property="og:title" content="{esc((title if article else NAME).lower())}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og}">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/assets/site.css">
<script type="application/ld+json">{json.dumps(ld)}</script>
</head>
<body{' class="has-music"' if music else ''}>
<header>
<a class="title" href="/">{NAME}</a>
<nav>{links}{THEME_BUTTON}</nav>
</header>
{body}
<footer>
<div class="foot"><span>pawan kalyan</span><nav>{socials}</nav></div>
{plinth}
</footer>
{music}<script>{NAV_JS}</script>
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


def prepare_book(b):
    """books uploaded from the sandbox come with only a pdf. the cover is its
    first page and the page count is read off the file."""
    pdf = b.get("pdf")
    if not pdf or (b.get("cover") and b.get("pages")):
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
    return b


def book_card(b, big=False):
    meta = " · ".join(x for x in (b.get("year", ""), f'{b["pages"]} pages' if b.get("pages") else "", "free pdf") if x)
    # the cover's size is known when it is made from the pdf, so the page keeps its room while it loads
    size = f' width="{b["cover_size"][0]}" height="{b["cover_size"][1]}"' if b.get("cover_size") else ""
    cover = f'<a href="{b["pdf"]}" download class="cover-link"><img class="cover" src="{b["cover"]}" alt="cover of {esc(b["title"])}"{size} loading="lazy" decoding="async"></a>' if b.get("cover") else ""
    code = f'<a class="code-link" href="{b["code"]}" download>source code <span>{size_of(b["code"])}</span></a>' if b.get("code") else ""
    blurb = f'<p class="note">{esc(b["blurb"])}</p>' if big and b.get("blurb") else ""
    subtitle = f'<p class="subtitle">{esc(b["subtitle"])}</p>' if b.get("subtitle") else ""
    return f"""<div class="book{" big" if big else ""}">
{cover}
<div>
<h3>{esc(b["title"])}</h3>
{subtitle}
{blurb}
<p class="meta">{esc(meta)}</p>
<div class="actions"><a class="button" href="{b["pdf"]}" download>download the pdf <span>{size_of(b["pdf"])}</span></a>{code}</div>
</div>
</div>"""


def books_page(entries):
    if not entries:
        return
    body = f"""<main>
<div class="head"><div>
<h1>books i write</h1>
<p class="lede-small">free to download, all of them.</p>
</div>{art("cherubs")}</div>
{"".join(book_card(b, big=True) for b in entries)}
</main>"""
    write("/books/", layout(title="books", description=entries[0].get("blurb", ""), path="/books/", body=body, nav="/books/",
                            og_image=entries[0].get("cover", DEFAULT_OG)))


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
    og_card(SITE_OG, title=NAME, footer=f"{GOOD_AT}  ·  {LANGUAGES}", title_size=(150, 150), max_lines=1)
    for p in posts:
        if p.cover and og_wide_cover(p):
            p.share = p.og
            continue
        og_card(p.og, title=p.title.lower(), kicker=f"{NAME}  ·  writing",
                footer=f"{SITE.removeprefix('https://')}  ·  {p.minutes} min read  ·  {p.pretty_date}")


# ---------------------------------------------------------------- pages

def home(posts, entries):
    rows = "".join(
        f'<li><a href="{p.url}"><span class="t">{esc(p.title)}</span><time datetime="{p.date.isoformat()}">{p.pretty_date}</time></a></li>\n'
        for p in posts
    )
    paper_rows = "".join(
        f'<li><a href="{p["url"]}"><span class="t">{esc(p["title"])}</span><span class="d">{esc(p["codeName"])}</span></a></li>\n'
        for p in papers()
    )
    fav_rows = "".join(
        f'<li><a href="{p["url"]}"><span class="t">{esc(p["title"])}</span><span class="d">{esc(p["venue"].rsplit(", ", 1)[-1])}</span></a></li>\n'
        for p in favourites()
    )
    fav_html = ""
    if fav_rows:
        fav_html = f"""<section>
<h2 class="label"><a href="/papers/#favourites">papers i love</a> <span>{len(favourites())}</span></h2>
<ul class="rows">
{fav_rows}</ul>
</section>"""
    books_html = ""
    if entries:
        books_html = f"""<section>
<h2 class="label">books <span>{len(entries)}</span></h2>
{"".join(book_card(b) for b in entries)}
</section>"""
    body = f"""<main class="home">
<section class="hello">
{art("falling", eager=True)}
<p class="lede">i work on ml infra, databases and inference, and write down what breaks along the way.</p>
<dl class="facts">
<div><dt>good at</dt><dd>{GOOD_AT}</dd></div>
<div><dt>languages</dt><dd>{LANGUAGES}</dd></div>
</dl>
</section>
<div class="divider">{art("wings")}</div>
<section>
<h2 class="label">writing <span>{len(posts)}</span></h2>
<ul class="rows">
{rows}</ul>
</section>
{books_html}
<section>
<h2 class="label">papers i implement <span>{len(papers())}</span></h2>
<ul class="rows">
{paper_rows}</ul>
</section>
{fav_html}
</main>"""
    write("/index.html", layout(title=NAME, description=TAGLINE, path="/", body=body, nav="/"))


def article(post, posts):
    standfirst = f'<div class="standfirst"><p>{post.standfirst}</p></div>' if post.standfirst else ""
    tags = f'<p class="tags">{esc(", ".join(post.tags))}</p>' if post.tags else ""
    others = [p for p in posts if p is not post]
    more = ""
    if others:
        links = "".join(f'<li><a href="{p.url}"><span class="t">{esc(p.title)}</span><time>{p.pretty_date}</time></a></li>' for p in others)
        more = f'<section class="more"><h2 class="label">more writing</h2><ul class="rows">{links}</ul></section>'
    body = f"""<main>
<h1>{esc(post.title)}</h1>
<p class="byline"><span><time datetime="{post.date.isoformat()}">{post.pretty_date}</time></span><span>{post.minutes} min read</span></p>
{standfirst}
<article class="prose">
{post.html}
</article>
<div class="end">{art("oyster")}</div>
{tags}
{more}
</main>"""
    write(post.url, layout(
        title=post.title, description=post.description, path=post.url, body=body, nav="/",
        og_image=post.share, article=post,
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
    body = f"""<main>
<h1>papers i implement</h1>
<p class="lede-small">the ones i read with an editor open. each links to the code.</p>
{art("supper")}
{"".join(items)}
{fav_html}
</main>"""
    write("/papers/", layout(title="papers", description="research papers i implement, with the code.", path="/papers/", body=body, nav="/papers/"))


def not_found():
    body = f"""<main class="nf"><h1>404</h1><p>nothing here. <a href="/">back to the writing</a>.</p>{art("beasts")}</main>"""
    write("/404.html", layout(title="not found", description="page not found.", path="/404.html", body=body, nav=""))


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


def sitemap(posts, has_books):
    urls = ["/", "/papers/"] + (["/books/"] if has_books else []) + [p.url for p in posts]
    body = "".join(f"<url><loc>{SITE}{u}</loc></url>\n" for u in urls)
    write("/sitemap.xml", f'<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n')
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.copytree(ROOT / "assets", DIST / "assets")
    shrink_svgs()
    posts = sorted((Post(p) for p in (CONTENT / "posts").glob("*.md")), key=lambda p: p.date, reverse=True)
    entries = [prepare_book(b) for b in books()]
    og_cards(posts)
    home(posts, entries)
    for post in posts:
        article(post, posts)
    papers_page()
    books_page(entries)
    not_found()
    feed(posts)
    posts_json(posts)
    sitemap(posts, bool(entries))
    print(f"built {len(posts)} posts and {len(entries)} books into {DIST.name}/")


if __name__ == "__main__":
    main()
