"""Build the Wikipedia keyword index (SQLite FTS5) from the wikimedia/wikipedia parquet shards.

Usage (on argo):
  uv run python -m laya_qwen.wiki_index /mnt/hub/data/wikipedia/20231101.en ~/laya-data/wiki.db
"""

import sqlite3
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

CHUNK_WORDS = 250


def chunks(text: str):
    """Pack lines into ~CHUNK_WORDS-word passages, splitting only at line breaks unless a line is huge."""
    buf: list[str] = []
    n = 0
    for line in text.split("\n"):
        words = line.split()
        if not words:
            continue
        if len(words) > CHUNK_WORDS:  # very long paragraph: hard-split, topping up the current buffer first
            words = buf + words
            buf, n = [], 0
            while len(words) > CHUNK_WORDS:
                yield " ".join(words[:CHUNK_WORDS])
                words = words[CHUNK_WORDS:]
        if n + len(words) > CHUNK_WORDS and buf:
            yield " ".join(buf)
            buf, n = [], 0
        buf.extend(words)
        n += len(words)
    if buf:
        yield " ".join(buf)


def build(shard_dir: Path, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
            title, url UNINDEXED, text, tokenize = 'porter unicode61 remove_diacritics 2'
        );
        CREATE TABLE IF NOT EXISTS shards_done (name TEXT PRIMARY KEY);
        """
    )
    done = {r[0] for r in db.execute("SELECT name FROM shards_done")}
    shards = sorted(shard_dir.glob("train-*.parquet"))
    start = time.monotonic()
    total = 0
    for shard in shards:
        if shard.name in done:
            continue
        rows = []
        for batch in pq.ParquetFile(shard).iter_batches(columns=["title", "url", "text"], batch_size=2000):
            for title, url, text in zip(*(batch.column(c).to_pylist() for c in ("title", "url", "text"))):
                for passage in chunks(text):
                    rows.append((title, url, passage))
        with db:
            db.executemany("INSERT INTO passages (title, url, text) VALUES (?, ?, ?)", rows)
            db.execute("INSERT INTO shards_done VALUES (?)", (shard.name,))
        total += len(rows)
        print(f"{shard.name}: {len(rows):,} passages ({total:,} total, {time.monotonic() - start:.0f}s)", flush=True)
    print("optimizing index...", flush=True)
    db.execute("INSERT INTO passages(passages) VALUES ('optimize')")
    db.commit()
    print(f"done in {time.monotonic() - start:.0f}s", flush=True)


if __name__ == "__main__":
    build(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser())
