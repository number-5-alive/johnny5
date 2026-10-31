"""Code shelf packet API: GET /code/search over the docs index (MDN, DevDocs) and the Stack Overflow index.

Mounted on the maps shelf service (same tailnet-only binding). Every result names its source and vintage, and every
response lists the sources it searched with their vintages. Stack Overflow results carry the agreement signal
(question score, each answer's score and accepted flag) and attribution (post URLs, licence; author names with
attribution=true).
"""

import json
import os
import re
import sqlite3
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

CODE_DATA = Path(os.environ.get("CODE_DATA", "~/code-data")).expanduser()
INDEXES = {"docs": CODE_DATA / "code-docs.db", "so": CODE_DATA / "code-so.db"}
STOP = {"a", "an", "the", "of", "in", "on", "to", "for", "is", "are", "how", "do", "does", "i", "what", "and", "or",
        "with", "can", "my", "it", "be", "by", "from", "as", "at", "this", "that", "you"}

router = APIRouter()
_local = threading.local()


def conn(name: str) -> sqlite3.Connection | None:
    cache = getattr(_local, "dbs", None)
    if cache is None:
        cache = _local.dbs = {}
    if name not in cache:
        path = INDEXES[name]
        cache[name] = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False) if path.exists() else None
    return cache[name]


def fts(q: str, tag: str | None) -> str:
    terms = [t for t in re.findall(r"[A-Za-z0-9_]+", q.lower()) if t not in STOP]
    terms = list(dict.fromkeys(terms))
    if not terms:
        raise HTTPException(400, "query has no searchable terms")
    expr = " OR ".join(f'"{t}"' for t in terms)
    if tag:
        expr = f'tags : "{tag.lower()}" AND ({expr})'
    return expr


def sources(db: sqlite3.Connection) -> dict[str, dict]:
    return {s: {"source": s, "kind": k, "vintage": v, **json.loads(d or "{}")}
            for s, k, v, d in db.execute("SELECT source, kind, vintage, detail FROM sources")}


def label(source: str, info: dict) -> str:
    if source == "mdn":
        return "MDN Web Docs"
    if source.startswith("devdocs:"):
        return info.get("label") or source
    if source.startswith("so:"):
        return f"Stack Exchange data dump ({source[3:]})"
    return source


def packet(row, srcs: dict, attribution: bool) -> dict:
    rowid, title, url, text, source, score, doc, vintage, meta_json = row
    meta = json.loads(meta_json or "{}")
    if not attribution:
        meta.pop("question_author", None)
        meta.pop("question_author_id", None)
        for a in meta.get("answers", []):
            a.pop("author", None)
            a.pop("author_id", None)
    info = srcs.get(source, {})
    return {"source": source, "source_label": label(source, info), "vintage": vintage,
            "source_vintage": info.get("vintage"), "title": title, "url": url, "doc": doc,
            "bm25": round(score, 3), "text": text, "meta": meta}


@router.get("/code/search")
def code_search(q: str, source: str = Query("all", pattern="^(all|so|docs)$"),
                tag: str | None = Query(None, description="tag filter, e.g. python (SO tags; docs language)"),
                limit: int = Query(8, ge=1, le=30), attribution: bool = False):
    names = ["docs", "so"] if source == "all" else [source]
    expr = fts(q, tag)
    results, searched = [], []
    for name in names:
        db = conn(name)
        if db is None:
            searched.append({"index": name, "available": False})
            continue
        srcs = sources(db)
        searched += [{"index": name, "available": True, "source": s, "source_label": label(s, i),
                      "vintage": i.get("vintage")} for s, i in srcs.items()]
        rows = db.execute(
            "SELECT p.rowid, p.title, p.url, p.text, p.source, bm25(passages, 5.0, 0.0, 1.0, 2.0, 0.0) AS s, "
            "m.doc, m.vintage, m.meta FROM passages p JOIN passage_meta m ON m.passage_rowid = p.rowid "
            "WHERE passages MATCH ? ORDER BY s LIMIT ?", (expr, limit)).fetchall()
        results += [packet(r, srcs, attribution) for r in rows]
    results.sort(key=lambda r: r["bm25"])  # bm25: lower is better; scales differ slightly between indexes
    return {"query": q, "source": source, "tag": tag, "count": len(results[:limit]), "results": results[:limit],
            "provenance": searched}
