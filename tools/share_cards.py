"""draws the picture a link to each page unfurls into: a typed sheet on the desk.

    pip install pillow
    python tools/share_cards.py

writes 1200x630 jpegs to assets/share, using edge or chrome to lay out the type.
run it again after adding a post, because every sheet carries the sheet count.
"""

import base64
import html
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build  # noqa: E402

OUT = ROOT / "assets" / "share"
BROWSERS = [
    os.environ.get("BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    shutil.which("msedge") or "",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def data_uri(data, kind):
    return f"data:{kind};base64,{base64.b64encode(data).decode()}"


def font(name):
    return data_uri((ROOT / "assets" / "fonts" / name).read_bytes(), "font/woff2")


CSS = f"""
@font-face {{ font-family: type; src: url({font("cmuntt.woff2")}); font-weight: 400; }}
@font-face {{ font-family: type; src: url({font("cmuntb.woff2")}); font-weight: 700; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 1200px; height: 630px; overflow: hidden; }}
body {{ position: relative; font-family: type, monospace; color: #23211d;
  background: radial-gradient(ellipse 900px 620px at 72% 45%, #c8c0ad 0%, #bdb5a2 62%, #b1a994 100%); }}
.ribbon {{ position: absolute; inset: 0 0 auto 0; height: 6px; background: #b8402f; z-index: 3; }}
.sheet {{ position: absolute; left: 100px; top: 40px; width: 760px; height: 700px; padding: 54px 62px 0;
  background: #f6f2e7; border-top-left-radius: 44px; transform: rotate(-1.3deg);
  box-shadow: 0 2px 3px rgba(40, 32, 20, .18), 0 14px 34px rgba(40, 32, 20, .24); }}
.head {{ display: flex; justify-content: space-between; align-items: baseline; padding-bottom: 14px;
  border-bottom: 1.5px solid #23211d; font-size: 16px; }}
.mark {{ font-family: "Yu Mincho", "MS Mincho", serif; margin-right: 6px; }}
.meta {{ margin-top: 46px; font-size: 16px; color: #7c766a; }}
.title {{ margin-top: 12px; font-size: 40px; line-height: 1.38; font-weight: 700; }}
.home {{ margin-top: 14px; font-size: 54px; line-height: 1.2; font-weight: 700; }}
.ja {{ font-family: "Yu Mincho", "MS Mincho", serif; font-weight: 400; font-size: 34px; margin-left: 14px; letter-spacing: 6px; }}
.desc {{ margin-top: 20px; max-width: 470px; font-size: 19px; line-height: 1.72; color: #4b4740; }}
.caret {{ display: inline-block; width: 12px; height: 21px; margin-left: 3px; background: #23211d; vertical-align: -3px; }}
.rows {{ margin-top: 22px; padding-top: 14px; border-top: 1.5px dotted #b9b09d; list-style: none; font-size: 16.5px; }}
.rows li {{ display: flex; align-items: baseline; gap: 10px; line-height: 2; }}
.no {{ color: #7c766a; }}
.t {{ max-width: 430px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.dots {{ flex: 1; border-bottom: 1.5px dotted #b9b09d; transform: translateY(-5px); }}
.right {{ color: #7c766a; }}
.wall {{ display: grid; grid-template-columns: repeat(6, 94px); gap: 12px; margin-top: 26px; }}
.wall img {{ width: 94px; height: 94px; object-fit: cover; display: block; box-shadow: 0 2px 5px rgba(40, 32, 20, .3); }}
.note {{ position: absolute; left: 898px; top: 236px; width: 240px; padding: 18px 20px 20px 42px; background: #efe7d6;
  transform: rotate(2deg); box-shadow: 0 8px 16px rgba(40, 32, 20, .22); font-size: 15px; line-height: 1.75; z-index: 2; }}
.note::before {{ content: ""; position: absolute; left: 17px; top: 15px; width: 12px; height: 12px; border-radius: 50%;
  background: #a39c8c; box-shadow: inset 0 1px 1px rgba(0, 0, 0, .3); }}
.note b {{ display: block; }}
.note span {{ color: #7c766a; display: block; }}
.cover {{ position: absolute; left: 900px; top: 112px; width: 240px; transform: rotate(2.5deg);
  box-shadow: 0 12px 24px rgba(40, 32, 20, .34); z-index: 2; }}
"""

# the sheet runs off the bottom of the card, so text has to stop before the edge
FIT = """
document.fonts.ready.then(() => {
  const LIMIT = 540;
  const title = document.querySelector('.title'), desc = document.querySelector('.desc');
  const bottom = el => el.offsetTop + el.offsetHeight;
  if (title) {
    let size = 40;
    while (size > 28 && title.offsetHeight / (size * 1.38) > 4.2) title.style.fontSize = (size -= 1) + 'px';
  }
  if (desc) {
    let words = desc.textContent.split(' ');
    while (words.length > 1 && bottom(desc) > LIMIT) {
      words.pop();
      desc.textContent = words.join(' ') + ' \\u2026';
    }
    if (bottom(desc) > LIMIT) desc.remove();
  }
});
"""


def esc(text):
    return html.escape(str(text))


def page(right, body, side):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="ribbon"></div>
<div class="sheet"><div class="head"><span><span class="mark" lang="ja">{build.JA[0]}</span>pawan.2026</span><span>{esc(right)}</span></div>
{body}</div>
{side}
<script>{FIT}</script></body></html>"""


def note(first="pawan kalyan", *rest):
    lines = "".join(f"<span>{esc(line)}</span>" for line in rest or ["cintu07.github.io"])
    return f'<div class="note"><b>{esc(first)}</b>{lines}</div>'


def rows(items):
    cells = "".join(
        f'<li><span class="no">{esc(no)}</span><span class="t">{esc(title)}</span><span class="dots"></span><span class="right">{esc(right)}</span></li>'
        for no, title, right in items
    )
    return f'<ul class="rows">{cells}</ul>'


def text_card(right, meta, title, desc, side=None):
    body = f'<p class="meta">{esc(meta)}</p><h1 class="title">{esc(title.lower())}</h1><p class="desc">{esc(desc.lower())}</p>'
    return page(right, body, side or note())


def home_card(posts, books, pictures):
    n = len(posts)
    latest = [(f"{n - i:02d}.", p.title.lower(), p.date.strftime("%d.%m.%y")) for i, p in enumerate(posts[:4])]
    body = f"""<p class="meta">long posts on ml infra, databases and inference</p>
<h1 class="home">pawan kalyan<span class="ja" lang="ja">{build.JA}</span></h1>
<p class="desc" style="margin-top:10px">i build database and inference stuff and break it a lot. this is where i write down why.<span class="caret"></span></p>
{rows(latest)}"""
    side = note("cintu07.github.io", f"{n} sheets, {len(books)} books,", f"{len(pictures)} pictures pinned up")
    return page("writing, papers, books, gallery", body, side)


def gallery_card(pictures):
    thumbs = "".join(f'<img src="{thumb(g)}" alt="">' for g in pictures[:12])
    body = f"""<p class="meta">prints, stamps, pixel art</p><h1 class="title">gallery</h1>
<div class="wall">{thumbs}</div>"""
    return page("gallery", body, note("pawan kalyan", f"{len(pictures)} pictures", "cintu07.github.io"))


def thumb(g):
    return data_uri((ROOT / "assets" / "gallery" / f"{g['name']}-t.webp").read_bytes(), "image/webp")


def papers_card(papers):
    body = f"""<p class="meta">read with an editor open</p><h1 class="title">papers i implement</h1>
<p class="desc">research papers i implement, with the code.</p>
{rows((f"p{i}.", p["title"].lower(), p["codeName"]) for i, p in enumerate(papers, 1))}"""
    return page("papers", body, note())


def books_card(books):
    body = f"""<p class="meta">free to download, all of them</p><h1 class="title">books i write</h1>
{rows((f"b{i}.", b["title"].lower(), b.get("year", "")) for i, b in enumerate(books, 1))}"""
    return page("books", body, note())


def cover_of(book):
    first_page = pymupdf.open(ROOT / book["pdf"].lstrip("/"))[0]
    return data_uri(first_page.get_pixmap(dpi=90).tobytes("jpeg"), "image/jpeg")


def book_card(book):
    pages = len(pymupdf.open(ROOT / book["pdf"].lstrip("/")))
    side = f'<img class="cover" src="{cover_of(book)}" alt="">'
    return text_card("book", f"book · {pages} pages · {book.get('year', '')}", book["title"], book.get("subtitle", ""), side)


def post_cards(posts):
    n = len(posts)
    for i, p in enumerate(posts):
        tag = p.tags[0] if p.tags else "writing"
        meta = f"{tag} · {p.minutes} min read · {p.date.strftime('%d %b %Y').lower()}"
        yield f"post-{p.slug}", text_card(f"sheet {n - i:02d} of {n:02d}", meta, p.title, p.description)


def shoot(browser, source, target, workdir):
    page_file = workdir / "card.html"
    page_file.write_text(source, encoding="utf-8")
    shot = workdir / "card.png"
    shot.unlink(missing_ok=True)
    subprocess.run(
        [browser, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--force-device-scale-factor=1",
         "--virtual-time-budget=4000", f"--user-data-dir={workdir / 'profile'}", "--window-size=1200,630",
         f"--screenshot={shot}", page_file.as_uri()],
        check=True, capture_output=True, timeout=120,
    )
    image = Image.open(io.BytesIO(shot.read_bytes())).convert("RGB")
    if image.size != (1200, 630):
        raise SystemExit(f"{target.name}: the browser drew {image.size}, expected 1200x630")
    image.save(target, quality=90, optimize=True)


def main():
    browser = next((b for b in BROWSERS if b and Path(b).exists()), None)
    if not browser:
        raise SystemExit("no edge or chrome found; set BROWSER to one")
    posts = sorted((build.Post(p) for p in (build.CONTENT / "posts").glob("*.md")), key=lambda p: p.date, reverse=True)
    books, papers, pictures = build.books(), build.papers(), build.gallery()
    cards = [
        ("site", home_card(posts, books, pictures)),
        ("page-gallery", gallery_card(pictures)),
        ("page-papers", papers_card(papers)),
        ("page-books", books_card(books)),
        *((f"book-{build.book_slug(b['title'])}", book_card(b)) for b in books),
        *post_cards(posts),
    ]
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, source in cards:
            shoot(browser, source, OUT / f"{name}.jpg", Path(tmp))
            print(name)
    print(json.dumps({"cards": len(cards)}))


if __name__ == "__main__":
    main()
