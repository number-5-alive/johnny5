"""Stage 7 corpus store: schema (DESIGN.md stage 7 Q5), article replacement shared by the monthly build and the daily
updater, and consistency checks (Q13 check 1).

The FTS5 `passages` table keeps the 2023 column order (title, url, text) so retrieval code and bm25 weights work
unchanged; `kind` (prose | table | infobox) is appended as an unindexed column.
"""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
    title, url UNINDEXED, text, kind UNINDEXED, tokenize = 'porter unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS articles (
    page_id    TEXT PRIMARY KEY,   -- Wikipedia page id
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    rev_id     INTEGER NOT NULL,   -- revision id of the text indexed
    rev_date   TEXT NOT NULL,      -- that revision's timestamp (real per-article date, not a snapshot floor)
    n_passages INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS articles_title_nocase ON articles(title COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS passage_article (
    passage_rowid INTEGER PRIMARY KEY,
    page_id       TEXT NOT NULL REFERENCES articles(page_id)
);
CREATE INDEX IF NOT EXISTS passage_article_page ON passage_article(page_id);
CREATE TABLE IF NOT EXISTS corpus_meta (key TEXT PRIMARY KEY, value TEXT);  -- snapshot date, source, last update
CREATE TABLE IF NOT EXISTS update_log (
    run_id    TEXT PRIMARY KEY,
    started   TEXT,
    finished  TEXT,
    status    TEXT,                 -- running | applied | failed_checks | error
    position  TEXT,                 -- stream resume point after this run
    changed   INTEGER,
    deleted   INTEGER,
    notes     TEXT
);
CREATE TABLE IF NOT EXISTS build_chunks_done (name TEXT PRIMARY KEY);
"""


def connect(path: Path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def set_meta(db: sqlite3.Connection, **kv) -> None:
    db.executemany("INSERT INTO corpus_meta VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   [(k, str(v)) for k, v in kv.items()])


def delete_article(db: sqlite3.Connection, page_id: str) -> int:
    rows = [r for (r,) in db.execute("SELECT passage_rowid FROM passage_article WHERE page_id = ?", (page_id,))]
    if rows:
        db.executemany("DELETE FROM passages WHERE rowid = ?", [(r,) for r in rows])
        db.execute("DELETE FROM passage_article WHERE page_id = ?", (page_id,))
    db.execute("DELETE FROM articles WHERE page_id = ?", (page_id,))
    return len(rows)


def replace_article(db: sqlite3.Connection, page_id: str, title: str, url: str, rev_id: int, rev_date: str,
                    passages: list, only_if_newer: bool = True) -> bool:
    """Replace one article's passages. passages: html_corpus.Passage list. Returns False if skipped as older."""
    if only_if_newer:
        row = db.execute("SELECT rev_id FROM articles WHERE page_id = ?", (page_id,)).fetchone()
        if row and row[0] >= rev_id:
            return False
    delete_article(db, page_id)
    for p in passages:
        cur = db.execute("INSERT INTO passages (title, url, text, kind) VALUES (?, ?, ?, ?)", (title, url, p.text, p.kind))
        db.execute("INSERT INTO passage_article VALUES (?, ?)", (cur.lastrowid, page_id))
    db.execute("INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?)", (page_id, title, url, rev_id, rev_date, len(passages)))
    return True


def consistency(db: sqlite3.Connection) -> dict:
    """Q13 check 1: every passage mapped, no orphans, per-article counts agree with the map."""
    n_pass = db.execute("SELECT count(*) FROM passages").fetchone()[0]
    n_map = db.execute("SELECT count(*) FROM passage_article").fetchone()[0]
    orphans = db.execute("SELECT count(*) FROM passage_article pa LEFT JOIN articles a USING (page_id) "
                         "WHERE a.page_id IS NULL").fetchone()[0]
    unmapped = db.execute("SELECT count(*) FROM passages p LEFT JOIN passage_article pa ON pa.passage_rowid = p.rowid "
                          "WHERE pa.passage_rowid IS NULL").fetchone()[0]
    bad_counts = db.execute("SELECT count(*) FROM articles a LEFT JOIN (SELECT page_id, count(*) c FROM passage_article "
                            "GROUP BY page_id) m USING (page_id) WHERE a.n_passages != coalesce(m.c, 0)").fetchone()[0]
    ok = n_pass == n_map and orphans == 0 and unmapped == 0 and bad_counts == 0
    return {"ok": ok, "passages": n_pass, "mapped": n_map, "orphan_mappings": orphans, "unmapped_passages": unmapped,
            "articles_with_wrong_count": bad_counts}
