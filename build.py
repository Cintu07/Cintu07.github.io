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
DEFAULT_OG = "/assets/img/og.png"
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


def figure(m):
    alt, src = m.group(1), m.group(2)
    caption = f"<figcaption>{alt}</figcaption>" if alt.strip() else ""
    return f'<figure><img src="{src}" alt="{alt}" loading="lazy">{caption}</figure>'


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
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="theme-color" content="#f8f4ea">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical}">
<link rel="alternate" type="application/rss+xml" title="{NAME}" href="/feed.xml">
<link rel="icon" href="/assets/img/icon.png">
<link rel="preload" href="/assets/fonts/et-book-roman.woff2" as="font" type="font/woff2" crossorigin>
<meta property="og:site_name" content="{NAME}">
<meta property="og:type" content="{"article" if article else "website"}">
<meta property="og:title" content="{esc(title if article else NAME)}">
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
<footer>
<span>set in et book. no trackers, no cookies, no javascript.</span>
<nav><a href="/feed.xml">rss</a></nav>
</footer>
</body>
</html>
"""


def write(path, text):
    target = DIST / path.lstrip("/")
    if target.suffix == "":
        target = target / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def home(posts):
    rows = "".join(
        f'<li><span><time datetime="{p.date.isoformat()}">{p.pretty_date}</time></span><a href="{p.url}">{esc(p.title)}</a></li>\n'
        for p in posts
    )
    body = f"""<main>
<p>i write about the things i build and what broke.</p>
<div class="skills">
<p><b>good at</b> {GOOD_AT}</p>
<p><b>languages</b> {LANGUAGES}</p>
</div>
<h2>writing</h2>
<ul class="blog-posts">
{rows}</ul>
</main>"""
    write("/index.html", layout(title=NAME, description=TAGLINE, path="/", body=body, nav="/"))


def article(post, posts):
    standfirst = f'<div class="standfirst"><p>{post.standfirst}</p></div>' if post.standfirst else ""
    tags = f'<p class="tags">{esc(", ".join(post.tags))}</p>' if post.tags else ""
    others = [p for p in posts if p is not post]
    more = ""
    if others:
        links = "".join(f'<p><a href="{p.url}">{esc(p.title)}</a></p>' for p in others)
        more = f'<section class="more"><h2>more writing</h2>{links}</section>'
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
        og_image=post.cover or DEFAULT_OG, article=post,
    ))


def papers_page():
    items = []
    for p in papers():
        items.append(f"""<div class="item">
<h2><a href="{p["url"]}">{esc(p["title"])}</a></h2>
<p class="by">{esc(p["authors"])}, {esc(p["venue"])}</p>
<p class="note">{esc(p["note"])}</p>
<p class="links"><a href="{p["url"]}">paper</a><a href="{p["code"]}">{esc(p["codeName"])}, the code</a></p>
</div>""")
    body = f"""<main>
<h1>papers i implement</h1>
<p class="byline">the ones i read with an editor open. each links to the code.</p>
{"".join(items)}
</main>"""
    write("/papers/", layout(title="papers", description="research papers i implement, with the code.", path="/papers/", body=body, nav="/papers/"))


def books_page():
    entries = books()
    if not entries:
        return
    items = []
    for b in entries:
        by = ", ".join(x for x in (b.get("status", ""), b.get("year", "")) if x)
        link = f'<p class="links"><a href="{b["url"]}">{esc(b.get("linkText", "read it"))}</a></p>' if b.get("url") else ""
        items.append(f"""<div class="item">
<h2>{esc(b["title"])}</h2>
<p class="by">{esc(by)}</p>
<p class="note">{esc(b["blurb"])}</p>
{link}
</div>""")
    body = f"""<main>
<h1>books i write</h1>
{"".join(items)}
</main>"""
    write("/books/", layout(title="books", description="books by pawan kalyan.", path="/books/", body=body, nav="/books/"))


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


def sitemap(posts):
    urls = ["/", "/papers/"] + (["/books/"] if books() else []) + [p.url for p in posts]
    body = "".join(f"<url><loc>{SITE}{u}</loc></url>\n" for u in urls)
    write("/sitemap.xml", f'<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n')
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.copytree(ROOT / "assets", DIST / "assets")
    posts = sorted((Post(p) for p in (CONTENT / "posts").glob("*.md")), key=lambda p: p.date, reverse=True)
    home(posts)
    for post in posts:
        article(post, posts)
    papers_page()
    books_page()
    not_found()
    feed(posts)
    sitemap(posts)
    print(f"built {len(posts)} posts into {DIST.name}/")


if __name__ == "__main__":
    main()
