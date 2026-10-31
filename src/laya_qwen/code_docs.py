"""Code shelf, docs half: MDN Web Docs (mdn/content, Markdown) and DevDocs packages (db.json HTML) to FTS5 passages.

Passages are documentation sections: a heading travels with its body (MDN: split at "##", and at "###" when a
section is long; DevDocs: split at headings and at each API entry such as a Python function or class). Code examples
are kept as indented plain text. Freshness: MDN passages carry the page's last commit date; DevDocs passages carry
the package's build date and release.

Usage (on argo; sources on the hub):
  python -m laya_qwen.code_docs build OUT.db --mdn /mnt/hub/data/code/docs/mdn-content \
      --devdocs /mnt/hub/data/code/docs/devdocs
"""

import argparse
import json
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from selectolax.lexbor import LexborHTMLParser

from .code_so import SCHEMA
from .code_text import html_to_text, mdn_markdown_to_text

MAX_WORDS = 600
MDN_AREAS = ("javascript", "html", "css")
MDN_SKIP = {"specifications", "browser compatibility", "see also"}
MDN_BASE = "https://developer.mozilla.org/en-US/docs/"


def words(t: str) -> int:
    return len(t.split())


def anchor(heading: str) -> str:
    return re.sub(r"[^\w]+", "_", heading.strip().lower()).strip("_")


# ---------------------------------------------------------------- MDN

def mdn_dates(repo: Path) -> dict[str, str]:
    """Last commit date per MDN page path (one pass over the log)."""
    paths = [f"files/en-us/web/{a}" for a in MDN_AREAS]
    out = subprocess.run(["git", "-C", str(repo), "log", "--format=@%cI", "--name-only", "--", *paths],
                         capture_output=True, text=True, check=True).stdout
    dates, current = {}, None
    for line in out.splitlines():
        if line.startswith("@"):
            current = line[1:]
        elif line and line not in dates:
            dates[line] = current
    return dates


def mdn_sections(body: str) -> list[tuple[str, str]]:
    """(heading, markdown) sections: intro, then each "##" section; long ones split at "###"."""
    sections, head, buf = [], "", []
    for line in body.split("\n"):
        if line.startswith("## "):
            sections.append((head, "\n".join(buf)))
            head, buf = line[3:].strip(), []
        else:
            buf.append(line)
    sections.append((head, "\n".join(buf)))
    out = []
    for h, md in sections:
        if h.lower() in MDN_SKIP:
            continue
        if words(md) <= MAX_WORDS or "\n### " not in "\n" + md:
            out.append((h, md))
            continue
        sub_head, sub = h, []
        for line in md.split("\n"):
            if line.startswith("### "):
                out.append((sub_head, "\n".join(sub)))
                sub_head, sub = f"{h}: {line[4:].strip()}" if h else line[4:].strip(), []
            else:
                sub.append(line)
        out.append((sub_head, "\n".join(sub)))
    return out


def mdn_passages(repo: Path):
    head = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%H %cI"], capture_output=True, text=True,
                          check=True).stdout.split()
    dates = mdn_dates(repo)
    n_pages = 0
    for area in MDN_AREAS:
        for f in sorted((repo / "files/en-us/web" / area).rglob("index.md")):
            raw = f.read_text(encoding="utf-8")
            m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
            if not m:
                continue
            front = dict(re.findall(r"^([\w-]+):\s*(.*)$", m.group(1), re.M))
            title, slug = front.get("title", "").strip("\"'"), front.get("slug", "").strip()
            rel = str(f.relative_to(repo))
            n_pages += 1
            for h, md in mdn_sections(raw[m.end():]):
                md = re.sub(r"^(\s*)- : ", r"\1  ", md, flags=re.M)  # definition-list bodies
                text = mdn_markdown_to_text(md).strip("\n")
                if words(text) < 5:
                    continue
                full = f"{h}\n\n{text}" if h else text
                subs = [x.strip() for x in re.findall(r"^### (.+)$", md, re.M)]
                shown = f"{h} ({', '.join(subs)})" if h and subs else h
                url = MDN_BASE + slug + (f"#{anchor(h.split(': ')[-1])}" if h else "")
                yield ("mdn", f"{title} — {shown}" if h else title, url, full, area,
                       {"doc": rel, "vintage": dates.get(rel) or head[1],
                        "meta": {"page": title, "section": h, "page_type": front.get("page-type"),
                                 "commit_date": dates.get(rel), "repo_commit": head[0], "path": rel,
                                 "license": "CC BY-SA 2.5 (prose), CC0 (code examples)"}})
    yield ("__source__", "mdn", {"kind": "docs", "vintage": head[1][:10],
                                 "detail": {"repo": "https://github.com/mdn/content", "commit": head[0],
                                            "commit_date": head[1], "areas": MDN_AREAS, "pages": n_pages}})


# ---------------------------------------------------------------- DevDocs

ENTRY_DL = re.compile(r"\b(py|function|method|class|attribute|data|exception|decorator|property)\b")


def _flatten(node):
    """Top-level blocks, descending through wrapper sections/divs that contain headings."""
    for child in node.iter(include_text=False):
        if child.tag in ("section", "div") and child.css_first("h1, h2, h3, h4, dl"):
            yield from _flatten(child)
        else:
            yield child


def devdocs_sections(page_html: str, page_title: str) -> list[tuple[str, str, str]]:
    """(heading, anchor, html) sections for one DevDocs page."""
    tree = LexborHTMLParser(f"<div>{page_html}</div>")
    root = tree.body.child
    sections, head, anc, buf = [], page_title, "", []

    def flush():
        if buf:
            sections.append((head, anc, "".join(buf)))

    for block in _flatten(root):
        tag = block.tag
        if tag in ("h1", "h2", "h3", "h4"):
            flush()
            buf = [block.html]
            head = block.text(deep=True).strip().rstrip("¶").strip() or head
            anc = block.attributes.get("id") or ""
            continue
        dt = block.css_first("dt[id]") if tag == "dl" else None
        if dt is not None and ENTRY_DL.search(block.attributes.get("class") or "py"):
            flush()
            sig = re.sub(r"\s+", " ", dt.text(deep=True)).strip().rstrip("¶").strip()
            sections.append((sig, dt.attributes.get("id") or "", block.html))
            buf = []
            continue
        buf.append(block.html)
    flush()
    return sections


def split_long(text: str) -> list[str]:
    if words(text) <= MAX_WORDS:
        return [text]
    out, cur = [], []
    for para in text.split("\n\n"):
        if cur and words("\n\n".join(cur + [para])) > MAX_WORDS:
            out.append("\n\n".join(cur))
            cur = []
        cur.append(para)
    if cur:
        out.append("\n\n".join(cur))
    return out


def devdocs_passages(pkg_dir: Path):
    for doc in json.loads((pkg_dir / "catalogue.json").read_text()):
        slug = doc["slug"]
        if not (pkg_dir / f"{slug}.db.json").exists() or not (pkg_dir / f"{slug}.index.json").exists():
            print(f"devdocs:{slug}: package files missing, skipped", flush=True)
            continue
        db = json.loads((pkg_dir / f"{slug}.db.json").read_text())
        index = json.loads((pkg_dir / f"{slug}.index.json").read_text())
        page_names = {}
        for e in index.get("entries", []):
            page_names.setdefault(e["path"].split("#")[0], e["name"])
        built = datetime.fromtimestamp(doc["mtime"], timezone.utc).strftime("%Y-%m-%d")
        source = f"devdocs:{slug}"
        label = f"DevDocs-{doc['name']} {doc.get('release', '')}".strip()
        for path, page_html in db.items():
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, re.S)
            h1_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h1.group(1))).strip().rstrip("¶").strip() if h1 else ""
            page_title = h1_text or page_names.get(path) or path
            for head, anc, sect_html in devdocs_sections(page_html, page_title):
                text = html_to_text(sect_html)
                if words(text) < 5:
                    continue
                for i, part in enumerate(split_long(text)):
                    if i:
                        part = f"{head} (continued)\n\n{part}"
                    title = head if head == page_title else f"{page_title} — {head}"
                    url = f"https://devdocs.io/{slug}/{path}" + (f"#{anc}" if anc else "")
                    yield (source, title, url, part, slug.split("~")[0],
                           {"doc": f"{slug}/{path}", "vintage": built,
                            "meta": {"package": slug, "release": doc.get("release"), "package_date": built,
                                     "page": page_title, "section": head, "label": label,
                                     "home": (doc.get("links") or {}).get("home"),
                                     "attribution": re.sub(r"<[^>]+>", "", doc.get("attribution", ""))[:300]}})
        yield ("__source__", source, {"kind": "docs", "vintage": built,
                                      "detail": {"label": label, "release": doc.get("release"), "package_date": built,
                                                 "pages": len(db), "home": (doc.get("links") or {}).get("home")}})


# ---------------------------------------------------------------- build

def build(out: Path, mdn: Path | None, devdocs: Path | None) -> None:
    out.unlink(missing_ok=True)
    db = sqlite3.connect(out)
    db.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;" + SCHEMA)
    t0, counts = time.time(), {}
    gens = ([mdn_passages(mdn)] if mdn else []) + ([devdocs_passages(devdocs)] if devdocs else [])
    for gen in gens:
        for item in gen:
            if item[0] == "__source__":
                _, source, info = item
                db.execute("INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?)",
                           (source, info["kind"], info["vintage"], json.dumps(info["detail"]),
                            datetime.now(timezone.utc).isoformat(timespec="seconds"), counts.get(source, 0)))
                print(f"{source}: {counts.get(source, 0):,} passages ({time.time() - t0:.0f}s)", flush=True)
                continue
            source, title, url, text, tags, extra = item
            cur = db.execute("INSERT INTO passages (title, url, text, tags, source) VALUES (?, ?, ?, ?, ?)",
                             (title, url, text, tags, source))
            db.execute("INSERT INTO passage_meta VALUES (?, ?, ?, ?)",
                       (cur.lastrowid, extra["doc"], extra["vintage"], json.dumps(extra["meta"])))
            counts[source] = counts.get(source, 0) + 1
    db.commit()
    db.execute("INSERT INTO passages(passages) VALUES ('optimize')")
    db.commit()
    print(f"BUILD_DONE {sum(counts.values()):,} passages ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("out", type=Path)
    b.add_argument("--mdn", type=Path)
    b.add_argument("--devdocs", type=Path)
    a = ap.parse_args()
    build(a.out, a.mdn, a.devdocs)
