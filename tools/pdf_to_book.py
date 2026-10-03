"""Turns a book PDF made with WeasyPrint back into chapters of HTML, so the
site can show it as web pages instead of a PDF viewer.

    pip install pymupdf pillow
    python tools/pdf_to_book.py assets/books/below-the-code-assembly.pdf below-the-code

writes content/books/<slug>/chapters.json and the diagrams under
assets/books/<slug>/fig/ as webp.
"""

import html
import json
import re
import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

HEADER_Y, FOOTER_Y = 45, 660
WRAP_X = 425          # a code line that reaches this far was wrapped by the page, not by the author
LIST_MARKER = re.compile(r"^(•|\d+\.)$")


def font_kind(span):
    f = span["font"]
    if f.startswith("Virgil"):
        return "hand"
    if f.startswith("Cascadia"):
        return "mono"
    if "Bold" in f:
        return "bold"
    return "text"


def esc(s):
    return html.escape(s, quote=False)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class Line:
    def __init__(self, raw):
        self.spans = [s for s in raw["spans"] if s["text"]]
        self.x0, self.y0, self.x1, self.y1 = raw["bbox"]
        self.text = "".join(s["text"] for s in self.spans)
        kinds = {font_kind(s) for s in self.spans if s["text"].strip()}
        self.kinds = kinds
        self.size = max((s["size"] for s in self.spans if s["text"].strip()), default=0)

    @property
    def all_hand(self):
        return self.kinds == {"hand"}

    @property
    def all_mono(self):
        return self.kinds == {"mono"}

    def inline_html(self):
        out = []
        for s in self.spans:
            k = font_kind(s)
            t = esc(s["text"])
            if k == "mono" and s["text"].strip():
                out.append(f"<code>{t.strip()}</code>")
            elif k == "bold" and s["text"].strip():
                lead = " " if s["text"].startswith(" ") else ""
                trail = " " if s["text"].endswith(" ") else ""
                out.append(f"{lead}<strong>{t.strip()}</strong>{trail}")
            else:
                out.append(t)
        return "".join(out)


def tidy_inline(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("-</code> <code>", "-")  # a flag broken at its hyphen, like -march
    s = s.replace("</code><code>", "").replace("</code> <code>", " ")
    s = s.replace("</strong><strong>", "").replace("</strong> <strong>", " ")
    s = re.sub(r"</code>\s+([,.;:!?)\]])", r"</code>\1", s)
    s = re.sub(r"([(\[])\s+<code>", r"\1<code>", s)
    s = re.sub(r"</strong>\s+([,.;:!?)])", r"</strong>\1", s)
    return s


def diagram_regions(page):
    """clusters of hand-drawn (curved) paths. callout boxes and rounded code
    backgrounds are single wide shapes and are left out."""
    paths = []
    for d in page.get_drawings():
        curves = sum(1 for it in d["items"] if it[0] == "c")
        if not curves:
            continue
        r = pymupdf.Rect(d["rect"])
        if curves <= 8 and r.width > 300:
            continue
        paths.append(r)
    clusters = []
    for r in paths:
        grown = pymupdf.Rect(r.x0 - 14, r.y0 - 14, r.x1 + 14, r.y1 + 14)
        hit = [c for c in clusters if c["rect"].intersects(grown)]
        merged = {"rect": pymupdf.Rect(r), "n": 1}
        for c in hit:
            merged["rect"] |= c["rect"]
            merged["n"] += c["n"]
            clusters.remove(c)
        clusters.append(merged)
    return [c["rect"] for c in clusters if c["n"] >= 6 and c["rect"].width * c["rect"].height > 3000]


def table_from(lines):
    header = [l for l in lines if l.all_hand]
    if not header:
        return None
    hy = min(l.y0 for l in header)
    head = sorted([l for l in header if abs(l.y0 - hy) < 2], key=lambda l: l.x0)
    cols = [l.x0 for l in head]
    if len(cols) < 2:
        return None
    body = [l for l in lines if l not in head]
    col0 = cols[0]
    starts = sorted({round(l.y0, 0) for l in body if abs(l.x0 - col0) < 6 or sum(1 for m in body if abs(m.y0 - l.y0) < 1.5) >= 2})
    rows = []
    for i, ys in enumerate(starts):
        ye = starts[i + 1] if i + 1 < len(starts) else 1e9
        cells = [[] for _ in cols]
        for l in body:
            if ys - 1.5 <= l.y0 < ye - 1.5:
                ci = max(j for j, cx in enumerate(cols) if l.x0 >= cx - 6) if l.x0 >= cols[0] - 6 else 0
                cells[ci].append(l)
        rows.append(["<br>".join(tidy_inline(x.inline_html()) for x in sorted(c, key=lambda m: m.y0)) for c in cells])
    th = "".join(f"<th>{esc(h.text.strip())}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows if any(r))
    return f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def page_items(page, pno, fig_dir, slug, fig_count):
    regions = diagram_regions(page)
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for raw in b.get("lines", []):
            l = Line(raw)
            if not l.text.strip() or l.y0 < HEADER_Y or l.y0 > FOOTER_Y:
                continue
            mid = pymupdf.Point((l.x0 + l.x1) / 2, (l.y0 + l.y1) / 2)
            if any(pymupdf.Rect(r.x0 - 4, r.y0 - 4, r.x1 + 4, r.y1 + 4).contains(mid) for r in regions):
                continue
            lines.append(l)

    items = []
    for r in regions:
        fig_count[0] += 1
        name = f"fig-{fig_count[0]:03d}.webp"
        clip = pymupdf.Rect(r.x0 - 8, r.y0 - 8, r.x1 + 8, r.y1 + 8) & page.rect
        pix = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=clip, alpha=False)
        Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(fig_dir / name, "WEBP", quality=88, method=6)
        items.append((r.y0, "fig", f"/assets/books/{slug}/fig/{name}"))

    # tables: rows of small text that line up in columns under a hand-lettered header
    table_lines = [l for l in lines if (l.all_hand and 9 <= l.size <= 9.4) or (not l.all_hand and 8.4 <= l.size <= 8.8 and l.kinds <= {"text", "mono", "bold"})]
    used = set()
    if table_lines:
        table_lines.sort(key=lambda l: l.y0)
        group = [table_lines[0]]
        groups = []
        for l in table_lines[1:]:
            if l.y0 - group[-1].y0 <= 26:
                group.append(l)
            else:
                groups.append(group)
                group = [l]
        groups.append(group)
        for g in groups:
            t = table_from(g)
            if t:
                items.append((min(l.y0 for l in g), "table", t))
                used.update(id(l) for l in g)
    lines = [l for l in lines if id(l) not in used]

    markers = [l for l in lines if LIST_MARKER.match(l.text.strip())]
    lines = [l for l in lines if l not in markers]
    for l in lines:
        m = next((mk for mk in markers if abs(mk.y0 - l.y0) < 1.5 and mk.x1 <= l.x0 + 2), None)
        l.marker = m.text.strip() if m else None

    for l in lines:
        if l.all_hand:
            t = l.text.strip()
            if l.size >= 20:
                items.append((l.y0, "title", t))
            elif 10.6 <= l.size <= 11.4 and re.match(r"^(Chapter|Appendix)\b", t):
                items.append((l.y0, "kicker", t))
            elif 14 <= l.size <= 15:
                items.append((l.y0, "h3" if t.lower() == "exercises" else "h2", t))
            elif l.size >= 11.5:
                items.append((l.y0, "h3", t))
            else:
                items.append((l.y0, "caption", t))
        elif l.all_mono and l.size < 8.2:
            items.append((l.y0, "code", l))
        else:
            items.append((l.y0, "text", l))
    items.sort(key=lambda it: (it[0], it[2].x0 if isinstance(it[2], Line) else 0))
    return items


def join(left, right):
    """lines of one paragraph; a word broken at its own hyphen (out-of-order) joins without a space"""
    if re.search(r"[A-Za-z]-$", left.rstrip()) and re.match(r"\s*[a-z]", right):
        return left.rstrip() + right.lstrip()
    return left + " " + right


def assemble(items):
    """turns page items into html blocks: lines become paragraphs, list items
    and code blocks, including ones that run over a page break"""
    blocks = []
    page = None
    for pno, y, kind, val in items:
        first_on_page = pno != page
        page = pno
        prev = blocks[-1] if blocks else None

        def same(k, gap):
            if not prev or prev["kind"] != k:
                return False
            return (y - prev["y"] <= gap) if not first_on_page else True

        if kind == "code":
            l = val
            char = l.size * 0.586
            if same("code", 26):
                b = prev
                if not first_on_page:
                    # a blank line inside the block shows up as a double gap
                    blanks = round((y - prev["y"]) / (l.size * 1.42)) - 1
                    if blanks > 0 and not b["wrap"]:
                        b["lines"].extend([""] * blanks)
            else:
                b = {"kind": "code", "lines": [], "x": l.x0, "y": y, "wrap": False}
                blocks.append(b)
            b["x"] = min(b["x"], l.x0)
            indent = max(0, round((l.x0 - b["x"]) / char))
            if b["wrap"] and b["lines"]:
                b["lines"][-1] += l.text.strip()
            else:
                b["lines"].append(" " * indent + l.text.rstrip())
            b["wrap"] = l.x1 >= WRAP_X
            b["y"] = y
            continue

        if kind == "text":
            l = val
            frag = l.inline_html()
            ends = bool(prev) and prev["kind"] in ("p", "li") and re.search(r"[.!?:]\s*(</code>|</strong>)?\s*$", prev["html"].rstrip())
            if l.marker:
                blocks.append({"kind": "li", "marker": l.marker, "html": frag, "x": l.x0, "y": y})
            elif prev and prev["kind"] == "li" and abs(l.x0 - prev["x"]) < 4 and (not first_on_page and y - prev["y"] < 18 or first_on_page and not ends):
                prev["html"] = join(prev["html"], frag)
                prev["y"] = y
            elif prev and prev["kind"] == "p" and (not first_on_page and y - prev["y"] < 17 or first_on_page and not ends):
                prev["html"] = join(prev["html"], frag)
                prev["y"] = y
            else:
                blocks.append({"kind": "p", "html": frag, "x": l.x0, "y": y})
            continue

        blocks.append({"kind": kind, "val": val, "y": y})
    return blocks


def to_html(blocks):
    out = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        k = b["kind"]
        if k == "p":
            out.append(f"<p>{tidy_inline(b['html'])}</p>")
        elif k == "li":
            ordered = b["marker"] != "•"
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(blocks) and blocks[i]["kind"] == "li" and (blocks[i]["marker"] != "•") == ordered:
                items.append(f"<li>{tidy_inline(blocks[i]['html'])}</li>")
                i += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        elif k == "code":
            code = "\n".join(b["lines"]).rstrip()
            out.append(f"<pre><code>{esc(code)}</code></pre>")
        elif k == "h2":
            out.append(f'<h2 id="{slugify(b["val"])}">{esc(b["val"])}</h2>')
        elif k == "h3":
            out.append(f"<h3>{esc(b['val'])}</h3>")
        elif k == "caption":
            nxt = blocks[i + 1]["kind"] if i + 1 < len(blocks) else ""
            cls = "code-caption" if nxt == "code" else "caption"
            out.append(f'<p class="{cls}">{esc(b["val"])}</p>')
        elif k == "table":
            out.append(b["val"])
        elif k == "fig":
            out.append(f'<figure><img src="{b["val"]}" alt="" loading="lazy"></figure>')
        i += 1
    return "\n".join(out)


def main(pdf_path, slug):
    doc = pymupdf.open(pdf_path)
    fig_dir = ROOT / "assets" / "books" / slug / "fig"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for old in [*fig_dir.glob("*.png"), *fig_dir.glob("*.webp")]:
        old.unlink()

    toc = [(t, p) for lvl, t, p in doc.get_toc() if lvl == 1 and not t.lower().startswith("contents")]
    chapters = []
    fig_count = [0]
    for idx, (raw_title, start) in enumerate(toc):
        end = toc[idx + 1][1] - 1 if idx + 1 < len(toc) else len(doc)
        items = []
        for pno in range(start - 1, end):
            for y, kind, val in page_items(doc[pno], pno, fig_dir, slug, fig_count):
                items.append((pno, y, kind, val))
        blocks = assemble(items)
        kicker = next((b["val"] for b in blocks if b["kind"] == "kicker"), "")
        # the outline has the whole title, the page splits long ones over two lines
        title = re.sub(r"^(Chapter \d+|Appendix [A-Z])", "", raw_title).strip()
        body = [b for b in blocks if b["kind"] not in ("kicker", "title")]
        chapters.append({
            "slug": slugify(title),
            "kicker": kicker,
            "title": title,
            "html": to_html(body),
        })
        print(f"{kicker:12} {title}  ({end - start + 1} pages, {sum(1 for b in body if b['kind']=='fig')} figures)")

    out = ROOT / "content" / "books" / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "chapters.json").write_text(json.dumps(chapters, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(chapters)} chapters, {fig_count[0]} figures")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
