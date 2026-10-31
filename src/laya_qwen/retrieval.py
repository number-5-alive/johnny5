"""Retrieval behind a pluggable interface.

A Retriever returns Passages that carry their re-rank score and a source tag, so callers can
judge weak results and mix sources (stage 7: delta-updated index, live web).

WikiIndexRetriever: FTS5 keyword search over the frozen Wikipedia snapshot, then
nomic-embed-text re-ranking.
"""

import math
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from . import ollama

WIKI_DB = Path(os.environ.get("LAYA_QWEN_WIKI_DB", "~/laya-data/wiki.db")).expanduser()
WIKI_SOURCE = "wikipedia-20261001"
EMBED_MODEL = "nomic-embed-text"
CANDIDATES = 50

STOPWORDS = set(
    """a an the of in on at to for from by with and or but is are was were be been being what which who whom whose
    when where why how did do does done had has have having this that these those it its as into than then there their
    his her he she they them we you i me my our your not no yes can could would should will shall may might must
    about after before during over under between through up down out off again further once all any both each few more
    most other some such only own same so too very s t just name year day month many much give tell""".split()
)


@dataclass
class Passage:
    title: str
    url: str
    text: str
    source: str  # which retriever produced it, e.g. "wikipedia-20231101"
    score: float = 0.0  # re-rank score (cosine similarity); comparable within one source
    bm25: float | None = None
    passage_id: int | None = None  # FTS5 rowid; stable for the life of an index
    page_id: str | None = None  # Wikipedia page id: stable per-article key
    rev_date: str | None = None  # see the articles table: currently the snapshot date, a floor


class Retriever(Protocol):
    source: str

    def search(self, question: str, k: int = 5) -> list[Passage]: ...


def fts_query(question: str, normalize: bool = False) -> str:
    terms = [t for t in re.findall(r"[\w']+", question.lower()) if t not in STOPWORDS and len(t) > 1]
    terms = list(dict.fromkeys(t.replace("'", "") for t in terms))
    if normalize:
        terms = list(dict.fromkeys(terms + expand_terms(question)))
    return " OR ".join(f'"{t}"' for t in terms if t)


ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
            "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth",
            "eighteenth", "nineteenth", "twentieth"]
SYNONYMS = [{"founded", "formed", "established", "created"}, {"born", "birth"}, {"died", "death"}]


def expand_terms(question: str) -> list[str]:
    """Extra keyword alternatives: two-digit years, ordinals both ways, a few verb synonyms."""
    q = question.lower()
    extra = []
    for yy in re.findall(r"(?:'|\u2019)(\d{2})\b", q):  # '04 -> 2004, '98 -> 1998
        extra.append(("20" if int(yy) <= 30 else "19") + yy)
    for n in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)\b", q):
        if 1 <= int(n) <= len(ORDINALS):
            extra.append(ORDINALS[int(n) - 1])
    for i, word in enumerate(ORDINALS, 1):
        if re.search(rf"\b{word}\b", q):
            extra.append(f"{i}{'st' if i % 10 == 1 and i != 11 else 'nd' if i % 10 == 2 and i != 12 else 'rd' if i % 10 == 3 and i != 13 else 'th'}")
    words = set(re.findall(r"[a-z]+", q))
    for group in SYNONYMS:
        if words & group:
            extra.extend(sorted(group - words))
    return extra


def _embed(texts: list[str]) -> list[list[float]]:
    resp = httpx.post(
        f"{ollama.OLLAMA_URL}/api/embed", json={"model": EMBED_MODEL, "input": texts}, timeout=120
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1.0)


@dataclass(frozen=True)
class RetrievalConfig:
    """Stage 2.1 options. The defaults reproduce stage 2 exactly."""

    per_article_cap: int | None = None  # max passages per article in the final top k
    expand_titles: bool = False  # add passages of articles whose title appears in the question
    expand_top_articles: int = 0  # add all passages of the top-N articles after the first re-rank
    normalize_query: bool = False  # two-digit years, ordinals, verb synonyms
    max_passages_per_article: int = 40  # limit when pulling a whole article in

    def name(self) -> str:
        parts = []
        if self.normalize_query:
            parts.append("norm")
        if self.expand_titles:
            parts.append("titles")
        if self.expand_top_articles:
            parts.append(f"top{self.expand_top_articles}")
        if self.per_article_cap:
            parts.append(f"cap{self.per_article_cap}")
        return "+".join(parts) or "stage2"


STAGE2 = RetrievalConfig()


def title_ngrams(question: str, max_n: int = 6) -> list[str]:
    """Candidate article titles from the question: capitalised or numeric spans, longest first."""
    tokens = [re.sub(r"(?:'s|\u2019s)$", "", t.strip(".,;:?!\"()\u201c\u201d")) for t in question.split()]
    tokens = [t for t in tokens if t]
    salient = lambda t: t[:1].isupper() or any(c.isdigit() for c in t)
    out = []
    for n in range(min(max_n, len(tokens)), 0, -1):
        for i in range(len(tokens) - n + 1):
            span = tokens[i : i + n]
            if not (salient(span[0]) and salient(span[-1])):
                continue
            if n == 1 and (len(span[0]) < 3 or span[0].isdigit() or not (
                any(c.isdigit() for c in span[0]) or "-" in span[0] or span[0].isupper())):
                continue  # single words only if code-like (NVS-01, ALCS), never bare numbers
            out.append(" ".join(span))
    return out


class WikiIndexRetriever:
    def __init__(self, db_path: Path = WIKI_DB, source: str = WIKI_SOURCE, config: RetrievalConfig = STAGE2):
        self.db_path = db_path
        self.source = source
        self.config = config
        self._local = threading.local()

    def _db(self) -> sqlite3.Connection:
        if not hasattr(self._local, "db"):
            self._local.db = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, check_same_thread=False)
        return self._local.db

    def keyword_search(self, question: str, limit: int = CANDIDATES) -> list[Passage]:
        q = fts_query(question, normalize=self.config.normalize_query)
        if not q:
            return []
        rows = self._db().execute(
            # Title matches weigh 5x body matches.
            "SELECT rowid, title, url, text, bm25(passages, 5.0, 0.0, 1.0) AS s FROM passages "
            "WHERE passages MATCH ? ORDER BY s LIMIT ?",
            (q, limit),
        ).fetchall()
        hits = [Passage(title=t, url=u, text=x, source=self.source, bm25=s, passage_id=r) for r, t, u, x, s in rows]
        self._attach_articles(hits)
        return hits

    def _attach_articles(self, hits: list[Passage]) -> None:
        if not hits:
            return
        db = self._db()
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'passage_article'").fetchone():
            return  # index built before the article tables existed
        marks = ",".join("?" * len(hits))
        rows = db.execute(
            "SELECT pa.passage_rowid, a.page_id, a.rev_date FROM passage_article pa "
            f"JOIN articles a ON a.page_id = pa.page_id WHERE pa.passage_rowid IN ({marks})",
            [p.passage_id for p in hits],
        ).fetchall()
        by_rowid = {r: (pid, rev) for r, pid, rev in rows}
        for p in hits:
            p.page_id, p.rev_date = by_rowid.get(p.passage_id, (None, None))

    def article_passages(self, page_id: str) -> list[Passage]:
        rows = self._db().execute(
            "SELECT p.rowid, p.title, p.url, p.text, a.rev_date FROM passage_article pa "
            "JOIN passages p ON p.rowid = pa.passage_rowid JOIN articles a ON a.page_id = pa.page_id "
            "WHERE pa.page_id = ? ORDER BY pa.passage_rowid LIMIT ?",
            (page_id, self.config.max_passages_per_article),
        ).fetchall()
        return [
            Passage(title=t, url=u, text=x, source=self.source, passage_id=r, page_id=page_id, rev_date=rev)
            for r, t, u, x, rev in rows
        ]

    def title_matches(self, question: str, limit: int = 3) -> list[str]:
        """Page ids of articles whose exact title (case-insensitive) is a span of the question."""
        found: list[str] = []
        covered: list[str] = []
        for span in title_ngrams(question):
            if len(found) >= limit:
                break
            if any(span.lower() in c.lower() for c in covered):
                continue  # a longer matching span already covers it
            row = self._db().execute("SELECT page_id FROM articles WHERE title = ? COLLATE NOCASE LIMIT 1", (span,)).fetchone()
            if row:
                found.append(row[0])
                covered.append(span)
        return found

    def _rerank(self, question: str, passages: list[Passage]) -> None:
        # nomic-embed-text expects task prefixes.
        vecs = _embed([f"search_query: {question}"] + [f"search_document: {p.title}. {p.text}" for p in passages])
        qv = vecs[0]
        for p, v in zip(passages, vecs[1:]):
            p.score = _cos(qv, v)

    def _add_articles(self, pool: list[Passage], page_ids: list[str]) -> list[Passage]:
        have = {p.passage_id for p in pool}
        new = [p for pid in page_ids for p in self.article_passages(pid) if p.passage_id not in have]
        return list({p.passage_id: p for p in new}.values())

    def search(self, question: str, k: int = 5) -> list[Passage]:
        cfg = self.config
        candidates = self.keyword_search(question)
        if cfg.expand_titles:
            candidates += self._add_articles(candidates, self.title_matches(question))
        if not candidates:
            return []
        self._rerank(question, candidates)
        ranked = sorted(candidates, key=lambda p: p.score, reverse=True)
        if cfg.expand_top_articles:
            top_ids = list(dict.fromkeys(p.page_id for p in ranked if p.page_id))[: cfg.expand_top_articles]
            extra = self._add_articles(ranked, top_ids)
            if extra:
                self._rerank(question, extra)
                ranked = sorted(ranked + extra, key=lambda p: p.score, reverse=True)
        if not cfg.per_article_cap:
            return ranked[:k]
        out, per = [], {}
        for p in ranked:
            key = p.page_id or p.url
            if per.get(key, 0) < cfg.per_article_cap:
                out.append(p)
                per[key] = per.get(key, 0) + 1
            if len(out) == k:
                break
        return out
