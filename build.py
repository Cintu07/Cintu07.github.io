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
    return f'<figure><img src="{src}" alt="{alt}"{svg_size(src)} loading="lazy">{caption}</figure>'


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
    socials = "".join(f'<a href="{href}"{"" if href.startswith("mailto:") else " rel=\"me noreferrer\""}>{label}</a>' for label, href in SOCIALS)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="theme-color" content="#ffffff">
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
<body>
<header>
<a class="title" href="/">{NAME}</a>
<nav>{links}</nav>
</header>
{body}
<footer><span>pawan kalyan</span><nav>{socials}</nav></footer>
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
        doc[0].get_pixmap(dpi=100).save(target, jpg_quality=86)
        b["cover"] = f"/assets/books/{name}"
    return b


def book_card(b, big=False):
    meta = " · ".join(x for x in (b.get("year", ""), f'{b["pages"]} pages' if b.get("pages") else "", "free pdf") if x)
    cover = f'<a href="{b["pdf"]}" download class="cover-link"><img class="cover" src="{b["cover"]}" alt="cover of {esc(b["title"])}" loading="lazy"></a>' if b.get("cover") else ""
    blurb = f'<p class="note">{esc(b["blurb"])}</p>' if big and b.get("blurb") else ""
    subtitle = f'<p class="subtitle">{esc(b["subtitle"])}</p>' if b.get("subtitle") else ""
    return f"""<div class="book{" big" if big else ""}">
{cover}
<div>
<h3>{esc(b["title"])}</h3>
{subtitle}
{blurb}
<p class="meta">{esc(meta)}</p>
<a class="button" href="{b["pdf"]}" download>download the pdf <span>{size_of(b["pdf"])}</span></a>
</div>
</div>"""


def books_page(entries):
    if not entries:
        return
    body = f"""<main>
<h1>books i write</h1>
<p class="lede-small">free to download, all of them.</p>
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


def og_cards(posts):
    og_card(SITE_OG, title=NAME, footer=f"{GOOD_AT}  ·  {LANGUAGES}", title_size=(150, 150), max_lines=1)
    for p in posts:
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
<p class="lede">i work on ml infra, databases and inference, and write down what breaks along the way.</p>
<dl class="facts">
<div><dt>good at</dt><dd>{GOOD_AT}</dd></div>
<div><dt>languages</dt><dd>{LANGUAGES}</dd></div>
</dl>
</section>
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
{tags}
{more}
</main>"""
    write(post.url, layout(
        title=post.title, description=post.description, path=post.url, body=body, nav="/",
        og_image=post.cover or post.og, article=post,
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
{"".join(items)}
{fav_html}
</main>"""
    write("/papers/", layout(title="papers", description="research papers i implement, with the code.", path="/papers/", body=body, nav="/papers/"))


def not_found():
    body = """<main class="nf"><h1>404</h1><p>nothing here. <a href="/">back to the writing</a>.</p></main>"""
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
            "og": absolute(p.cover or p.og),
            "minutes": p.minutes,
            "url": SITE + p.url,
            "markdown": body,
        })
    write("/posts.json", json.dumps(out, ensure_ascii=False))


def sitemap(posts, has_books):
    urls = ["/", "/papers/"] + (["/books/"] if has_books else []) + [p.url for p in posts]
    body = "".join(f"<url><loc>{SITE}{u}</loc></url>\n" for u in urls)
    write("/sitemap.xml", f'<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n')
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.copytree(ROOT / "assets", DIST / "assets")
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
