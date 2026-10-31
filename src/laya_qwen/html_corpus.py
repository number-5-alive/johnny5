"""Stage 7: Wikipedia article HTML (Parsoid / Enterprise) -> passages. DESIGN.md stage 7 Q2-Q4, Q14.

One parser for both the monthly Enterprise snapshot and the daily REST `page/html` fetches.

  prose    paragraphs and lists, with section headings as their own lines, packed with the same ~250-word chunker
           as the 2023 corpus (wiki_index.chunks)
  table    data tables: groups of rows, each passage repeating caption, section heading and column headers,
           rows written as "Header: value; ..."
  infobox  "Infobox: <title> — Label: value; ..."

Dropped: reference lists and citation markers, navboxes, hatnotes, edit links, coordinates, image captions and
figures, maintenance boxes, and the See also / References / External links / Further reading sections (plus the
other reference-list sections: Notes, Citations, Sources, Bibliography, Footnotes).
"""

import re
from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser

from .wiki_index import CHUNK_WORDS, chunks

DROP_SELECTORS = [
    "style", "script", "link", "meta",
    "sup.reference", "sup.mw-ref", "span.mw-ref", ".mw-references-wrap", "ol.references", ".reflist",
    ".navbox", ".navbox-styles", ".vertical-navbox", ".sidebar", ".hatnote", ".shortdescription", ".navbar",
    ".mw-editsection", "figure", "figcaption", ".thumb", ".gallery", ".mw-gallery-traditional",
    "#coordinates", ".geo-default", ".geo-nondefault", ".coordinates",
    ".ambox", ".mbox-small", ".metadata", ".sistersitebox", ".portalbox", ".side-box", ".noprint",
    ".mw-empty-elt", ".mw-cite-backlink",
]
SKIP_SECTIONS = {"see also", "references", "external links", "further reading",
                 "notes", "citations", "sources", "bibliography", "footnotes", "notes and references"}
HEADINGS = ("h2", "h3", "h4", "h5", "h6")


@dataclass
class Passage:
    title: str
    text: str
    kind: str  # prose | table | infobox
    section: str = ""


def clean(text: str) -> str:
    text = re.sub(r"\[\d+\]|\[[a-z]\]|\[citation needed\]", "", text)
    text = re.sub(r"[\ufeff\u200b\u200e\u200f]", "", text)  # zero-width marks left by coordinate templates
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?)\]])", r"\1", text)  # node_text joins inline nodes with spaces
    text = re.sub(r"([(\[])\s+", r"\1", text)
    return text.strip()


def node_text(node) -> str:
    return clean(node.text(separator=" "))


def nearest_table(node) -> int | None:
    p = node.parent
    while p is not None and p.tag != "table":
        p = p.parent
    return p.mem_id if p is not None else None


def table_grid(table) -> list[list[tuple[str, bool]]]:
    """Expand a table into a grid of (text, is_header) cells, honouring rowspan and colspan."""
    grid: list[list[tuple[str, bool]]] = []
    carry: dict[int, tuple[str, bool, int]] = {}  # column -> (text, is_header, rows left)
    for tr in table.css("tr"):
        if nearest_table(tr) != table.mem_id:
            continue  # row of a nested table
        row: list[tuple[str, bool]] = []
        col = 0
        cells = [c for c in tr.iter() if c.tag in ("td", "th")]
        for cell in cells:
            while col in carry:
                t, h, left = carry[col]
                row.append((t, h))
                carry[col] = (t, h, left - 1) if left > 1 else None
                if carry[col] is None:
                    del carry[col]
                col += 1
            text, is_h = node_text(cell), cell.tag == "th"
            span = int(re.sub(r"\D", "", cell.attributes.get("colspan") or "1") or 1)
            rspan = int(re.sub(r"\D", "", cell.attributes.get("rowspan") or "1") or 1)
            for _ in range(min(span, 20)):
                row.append((text, is_h))
                if rspan > 1:
                    carry[col] = (text, is_h, rspan - 1)
                col += 1
        while col in carry:  # trailing rowspans
            t, h, left = carry[col]
            row.append((t, h))
            if left > 1:
                carry[col] = (t, h, left - 1)
            else:
                del carry[col]
            col += 1
        if row:
            grid.append(row)
    return grid


def table_passages(title: str, section: str, table) -> list[Passage]:
    caption = table.css_first("caption")
    cap = node_text(caption) if caption else ""
    grid = table_grid(table)
    if not grid:
        return []
    header_rows = 0
    while header_rows < len(grid) and all(h for _, h in grid[header_rows]):
        header_rows += 1
    if header_rows:
        width = max(len(r) for r in grid[:header_rows])
        headers = [" / ".join(dict.fromkeys(r[i][0] for r in grid[:header_rows] if i < len(r) and r[i][0]))
                   for i in range(width)]
    else:
        headers = []
    context = " — ".join(x for x in (title, section, cap) if x)
    lines = []
    for row in grid[header_rows:]:
        parts = []
        for i, (val, _) in enumerate(row):
            if not val:
                continue
            h = headers[i] if i < len(headers) and headers[i] else ""
            parts.append(f"{h}: {val}" if h and h != val else val)
        if parts:
            lines.append("; ".join(dict.fromkeys(parts)) + ".")
    if not lines:
        return []
    head = f"Table: {context}." + (f" Columns: {', '.join(h for h in headers if h)}." if headers else "")
    budget = max(CHUNK_WORDS - len(head.split()), 50)
    out, buf, n = [], [], 0
    for line in lines:
        w = len(line.split())
        if buf and n + w > budget:
            out.append(Passage(title, head + " " + " ".join(buf), "table", section))
            buf, n = [], 0
        buf.append(line)
        n += w
    if buf:
        out.append(Passage(title, head + " " + " ".join(buf), "table", section))
    return out


def infobox_passages(title: str, box) -> list[Passage]:
    fields, current = [], ""
    for tr in box.css("tr"):
        hdr = tr.css_first(".infobox-header, .infobox-above, th[colspan]")
        label, data = tr.css_first(".infobox-label"), tr.css_first(".infobox-data")
        if label and data:
            fields.append(f"{node_text(label)}: {node_text(data)}")
        elif hdr and not data:
            current = node_text(hdr)
            if current and current != title:
                fields.append(f"[{current}]")
        elif data and not label:
            t = node_text(data)
            if t and len(t.split()) <= 40:
                fields.append(t)
    # Drop fields with no real value ("Coordinates: /") and headers with nothing under them ("[Location map]").
    fields = [f for f in fields if f and re.search(r"\w", f.split(":", 1)[-1])]
    fields = [f for i, f in enumerate(fields)
              if not (f.startswith("[") and (i + 1 == len(fields) or fields[i + 1].startswith("[")))]
    if not any(":" in f for f in fields):
        return []
    head = f"Infobox: {title} —"
    out, buf, n = [], [], len(head.split())
    for f in fields:
        w = len(f.split())
        if buf and n + w > CHUNK_WORDS:
            out.append(Passage(title, head + " " + "; ".join(buf) + ".", "infobox"))
            buf, n = [], len(head.split())
        buf.append(f)
        n += w
    if buf:
        out.append(Passage(title, head + " " + "; ".join(buf) + ".", "infobox"))
    return out


def parse_article(title: str, html: str) -> list[Passage]:
    tree = LexborHTMLParser(html)
    body = tree.body or tree.root
    for sel in DROP_SELECTORS:
        for node in body.css(sel):
            node.decompose()

    passages: list[Passage] = []
    for box in body.css("table.infobox"):
        passages += infobox_passages(title, box)
        box.decompose()

    prose_lines: list[str] = []
    section, skipping = "", False
    handled_tables = set()

    def walk(node):
        nonlocal section, skipping
        for child in node.iter(include_text=False):
            tag = child.tag
            if tag in HEADINGS:
                heading = node_text(child)
                level = int(tag[1])
                if level == 2:
                    skipping = heading.lower() in SKIP_SECTIONS
                elif skipping:
                    continue
                if not skipping and heading:
                    section = heading
                    prose_lines.append(heading)
                continue
            if skipping:
                continue
            if tag == "table":
                if child.mem_id in handled_tables:
                    continue
                handled_tables.add(child.mem_id)
                classes = child.attributes.get("class") or ""
                if "wikitable" in classes or "sortable" in classes or child.css_first("th"):
                    passages.extend(table_passages(title, section, child))
                continue
            if tag == "p":
                t = node_text(child)
                if t:
                    prose_lines.append(t)
            elif tag in ("ul", "ol"):
                for li in child.iter(include_text=False):
                    if li.tag == "li":
                        t = node_text(li)
                        if t:
                            prose_lines.append(t)
            elif tag == "dl":
                t = node_text(child)
                if t:
                    prose_lines.append(t)
            elif tag in ("section", "div", "blockquote", "center"):
                walk(child)

    walk(body)
    prose = [Passage(title, c, "prose") for c in chunks("\n".join(prose_lines))]
    return prose + passages
