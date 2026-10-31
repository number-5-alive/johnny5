"""Stage 7: build an FTS5 corpus from a Wikimedia Enterprise HTML snapshot (chunk tar.gz files of NDJSON).

Chunks are parsed in worker processes and written by the main process, one transaction per chunk, so the build
resumes chunk by chunk. Duplicate articles keep the highest revision id (Enterprise docs) through the same
replace_article used by the daily updater.

Usage (on argo):
  uv run python -m laya_qwen.wiki_html_index SNAPSHOT_DIR OUT.db [--workers N] [--limit-chunks N]
"""

import argparse
import json
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import wiki_store
from .html_corpus import parse_article


def parse_chunk(path: str) -> tuple[str, list, int]:
    """(chunk name, [(page_id, title, url, rev_id, rev_date, passages)], skipped) for one chunk tar.gz."""
    out, skipped = [], 0
    with tarfile.open(path, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".ndjson"):
                continue
            for line in tar.extractfile(member):
                rec = json.loads(line)
                html = (rec.get("article_body") or {}).get("html") or ""
                if not html or rec.get("namespace", {}).get("identifier", 0) != 0:
                    skipped += 1
                    continue
                passages = parse_article(rec["name"], html)
                out.append((str(rec["identifier"]), rec["name"], rec["url"], int(rec["version"]["identifier"]),
                            rec["date_modified"], passages))
    return Path(path).name, out, skipped


def build(snapshot_dir: Path, db_path: Path, workers: int = 8, limit_chunks: int | None = None) -> None:
    db = wiki_store.connect(db_path)
    db.executescript("PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;")
    snap = json.loads((snapshot_dir / "snapshot.json").read_text())
    done = {r for (r,) in db.execute("SELECT name FROM build_chunks_done")}
    chunks = sorted(snapshot_dir.glob("*.tar.gz"), key=lambda p: int(p.name.split("_chunk_")[1].split(".")[0]))
    todo = [str(c) for c in chunks if c.name not in done][: limit_chunks]
    start, articles, replaced_dupes, skipped_old = time.monotonic(), 0, 0, 0
    def results(pool):
        """Chunk results in order, with at most 2 x workers parsed chunks waiting in memory."""
        pending, queue = {}, list(todo)
        for i, path in enumerate(queue[: workers * 2]):
            pending[i] = pool.submit(parse_chunk, path)
        nxt = len(pending)
        for i in range(len(queue)):
            res = pending.pop(i).result()
            if nxt < len(queue):
                pending[nxt] = pool.submit(parse_chunk, queue[nxt])
                nxt += 1
            yield res

    with ProcessPoolExecutor(workers) as pool:
        for n, (name, records, skipped) in enumerate(results(pool), 1):
            with db:
                for page_id, title, url, rev_id, rev_date, passages in records:
                    existed = db.execute("SELECT 1 FROM articles WHERE page_id = ?", (page_id,)).fetchone()
                    if wiki_store.replace_article(db, page_id, title, url, rev_id, rev_date, passages):
                        articles += not existed
                        replaced_dupes += bool(existed)
                    else:
                        skipped_old += 1
                db.execute("INSERT INTO build_chunks_done VALUES (?)", (name,))
            print(f"[{n}/{len(todo)}] {name}: {len(records)} records, {skipped} skipped; total new articles "
                  f"{articles:,}, dupes replaced {replaced_dupes}, older dupes skipped {skipped_old} "
                  f"({time.monotonic() - start:.0f}s)", flush=True)
    complete = len(done) + len(todo) == len(chunks)
    wiki_store.set_meta(db, snapshot_identifier=snap.get("identifier"), snapshot_date=snap.get("date_modified", "")[:10],
                        snapshot_version=snap.get("version"), source_format="enterprise-html",
                        source=f"wikipedia-{snap.get('date_modified', '')[:10].replace('-', '')}-html",
                        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        build_complete=complete, chunks_built=len(done) + len(todo), chunks_total=len(chunks))
    db.commit()
    if complete:
        print("optimizing index...", flush=True)
        db.execute("INSERT INTO passages(passages) VALUES ('optimize')")
        db.commit()
    print(json.dumps(wiki_store.consistency(db)), flush=True)
    print("BUILD_DONE" if complete else "BUILD_PARTIAL", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("db", type=Path)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit-chunks", type=int)
    a = ap.parse_args()
    build(a.snapshot_dir.expanduser(), a.db.expanduser(), a.workers, a.limit_chunks)
