"""Article side tables for the Wikipedia index: a stable per-article key and revision date.

Adds `articles` and `passage_article` next to the FTS5 `passages` table without touching it,
so retrieval results are unchanged. Stage 7's delta updater uses passage_article to find and
replace one article's passages.

Usage (on argo):
  uv run python -m laya_qwen.wiki_articles build  /mnt/hub/data/wikipedia/20231101.en ~/laya-data/wiki.db
  uv run python -m laya_qwen.wiki_articles verify /mnt/hub/data/wikipedia/20231101.en ~/laya-data/wiki.db
"""

import random
import sqlite3
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

from .wiki_index import chunks

SNAPSHOT_DATE = "2023-11-01"

# Comments inside CREATE TABLE are kept in sqlite_master, so they travel with the database.
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS articles (
    page_id  TEXT PRIMARY KEY,  -- Wikipedia page id: stable across renames
    title    TEXT NOT NULL,
    url      TEXT NOT NULL,
    rev_date TEXT NOT NULL      -- PLACEHOLDER: set to the snapshot date ({SNAPSHOT_DATE}) for every article.
                                -- It is a floor (the article is at least this current), NOT a real per-article
                                -- revision date. Stage 7 replaces it with dates from the dump's stub-meta-current.
);
CREATE TABLE IF NOT EXISTS passage_article (
    passage_rowid INTEGER PRIMARY KEY,  -- rowid in the passages FTS5 table
    page_id       TEXT NOT NULL REFERENCES articles(page_id)
);
CREATE INDEX IF NOT EXISTS passage_article_page ON passage_article(page_id);
"""


def read_articles(shard_dir: Path):
    for shard in sorted(shard_dir.glob("train-*.parquet")):
        for batch in pq.ParquetFile(shard).iter_batches(columns=["id", "url", "title"], batch_size=50000):
            yield from zip(*(batch.column(c).to_pylist() for c in ("id", "url", "title")))


def build(shard_dir: Path, db_path: Path) -> None:
    start = time.monotonic()
    db = sqlite3.connect(db_path)
    db.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;" + SCHEMA)
    if db.execute("SELECT count(*) FROM articles").fetchone()[0]:
        raise SystemExit("articles already populated; drop articles and passage_article to rebuild")

    url_to_id: dict[str, str] = {}
    dup_urls = 0
    with db:
        for page_id, url, title in read_articles(shard_dir):
            if url in url_to_id:
                dup_urls += 1
                continue
            url_to_id[url] = page_id
            db.execute("INSERT INTO articles VALUES (?, ?, ?, ?)", (page_id, title, url, SNAPSHOT_DATE))
    print(f"articles: {len(url_to_id):,} (duplicate urls skipped: {dup_urls}) {time.monotonic() - start:.0f}s", flush=True)

    unmapped = 0
    batch = []
    with db:
        for rowid, url in db.execute("SELECT rowid, url FROM passages"):
            page_id = url_to_id.get(url)
            if page_id is None:
                unmapped += 1
                continue
            batch.append((rowid, page_id))
            if len(batch) >= 100000:
                db.executemany("INSERT INTO passage_article VALUES (?, ?)", batch)
                batch.clear()
        db.executemany("INSERT INTO passage_article VALUES (?, ?)", batch)
    mapped = db.execute("SELECT count(*) FROM passage_article").fetchone()[0]
    print(f"passage_article: {mapped:,} mapped, {unmapped:,} unmapped, {time.monotonic() - start:.0f}s", flush=True)


def verify(shard_dir: Path, db_path: Path, shards: int = 4, per_shard: int = 5, seed: int = 7) -> bool:
    """Whole-table consistency checks, then spot-check articles by re-chunking their source text."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'}  {label} {detail}", flush=True)

    n_passages = db.execute("SELECT count(*) FROM passages").fetchone()[0]
    n_mapped = db.execute("SELECT count(*) FROM passage_article").fetchone()[0]
    check("every passage is mapped", n_passages == n_mapped, f"({n_mapped:,}/{n_passages:,})")
    orphans = db.execute(
        "SELECT count(*) FROM passage_article pa LEFT JOIN articles a ON a.page_id = pa.page_id WHERE a.page_id IS NULL"
    ).fetchone()[0]
    check("every mapping points at an article", orphans == 0, f"({orphans} orphans)")
    mismatched = db.execute(
        "SELECT count(*) FROM passage_article pa JOIN passages p ON p.rowid = pa.passage_rowid "
        "JOIN articles a ON a.page_id = pa.page_id WHERE p.url != a.url OR p.title != a.title"
    ).fetchone()[0]
    check("passage title/url match their article", mismatched == 0, f"({mismatched} mismatched)")
    placeholder = db.execute("SELECT count(*) FROM articles WHERE rev_date != ?", (SNAPSHOT_DATE,)).fetchone()[0]
    check("rev_date is the snapshot placeholder everywhere", placeholder == 0)

    # Spot-check: pull an article's passages through the map and compare with its re-chunked source text.
    rng = random.Random(seed)
    all_shards = sorted(shard_dir.glob("train-*.parquet"))
    for shard in rng.sample(all_shards, shards):
        table = pq.read_table(shard, columns=["id", "title", "text"])
        for i in rng.sample(range(table.num_rows), per_shard):
            page_id, title, text = (table.column(c)[i].as_py() for c in ("id", "title", "text"))
            expected = list(chunks(text))
            got = db.execute(
                "SELECT p.title, p.text FROM passage_article pa JOIN passages p ON p.rowid = pa.passage_rowid "
                "WHERE pa.page_id = ? ORDER BY pa.passage_rowid",
                (page_id,),
            ).fetchall()
            same = [t for _, t in got] == expected and all(t == title for t, _ in got)
            check(f"{shard.name[:13]} page {page_id} '{title[:40]}'", same, f"({len(got)} passages, expected {len(expected)})")
    return ok


if __name__ == "__main__":
    cmd, shard_dir, db_path = sys.argv[1], Path(sys.argv[2]).expanduser(), Path(sys.argv[3]).expanduser()
    if cmd == "build":
        build(shard_dir, db_path)
    elif cmd == "verify":
        sys.exit(0 if verify(shard_dir, db_path) else 1)
    else:
        raise SystemExit(f"unknown command {cmd}")
