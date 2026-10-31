"""Design probe runner: SimpleQA Verified items through a frozen pipeline.

Mirrors laya_qwen.eval semantics exactly (same run_one, same metrics via
summarize) but loads the Verified CSV instead of the internal splits.
Corpus selection is entirely by the LAYA_QWEN_WIKI_DB env var, as with
every other run. Resumable: non-error rows already in the run's
answers.jsonl are skipped.

Usage:
  LAYA_QWEN_WIKI_DB=~/laya-data/wiki-staging.db \
    .venv/bin/python scripts/probe_verified.py [--limit N] [--run NAME]
"""

import argparse
import csv
import json
import os
import threading
import time
from pathlib import Path

from laya_qwen import eval as ev
from laya_qwen import simpleqa
from laya_qwen.pipelines import PIPELINES

ROOT = Path(__file__).resolve().parents[1]
VERIFIED_CSV = ROOT / "data" / "verified" / "simpleqa_verified.csv"
PIPELINE_NAME = "agree21_k15"


def load_verified() -> list[simpleqa.Item]:
    items = []
    with VERIFIED_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            items.append(
                simpleqa.Item(
                    id=int(row["original_index"]),
                    question=row["problem"],
                    answer=row["answer"],
                    topic=row.get("topic", ""),
                )
            )
    ids = [it.id for it in items]
    assert len(ids) == len(set(ids)), "original_index values are not unique"
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--run", default="probe-verified-full-2026-10-22")
    args = ap.parse_args()

    db_env = os.environ.get("LAYA_QWEN_WIKI_DB", "(default: live 2023 corpus)")
    db_resolved = str(Path(db_env).expanduser().resolve()) if db_env.startswith(("~", "/")) else db_env
    print(f"probe run={args.run} pipeline={PIPELINE_NAME}", flush=True)
    print(f"corpus env={db_env} resolved={db_resolved}", flush=True)

    pipeline = PIPELINES[PIPELINE_NAME]
    path = ev.answers_path(args.run)
    path.parent.mkdir(parents=True, exist_ok=True)
    done = {r["id"] for r in ev.load_rows(args.run) if r["grade"] != "error"}
    todo = [it for it in load_verified() if it.id not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"done={len(done)} todo={len(todo)}", flush=True)

    lock = threading.Lock()
    start = time.monotonic()
    for n, item in enumerate(todo, 1):
        row = ev.run_one(pipeline, item)
        with lock, path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        secs = row["meta"].get("seconds", "-")
        print(f"[{n}/{len(todo)}] {row['grade']:<13} {secs}s  {row['question'][:70]}", flush=True)
    print(f"elapsed {time.monotonic() - start:.0f}s", flush=True)
    print(f"corpus resolved at end={db_resolved}", flush=True)
    ev.summarize(args.run)


if __name__ == "__main__":
    main()
