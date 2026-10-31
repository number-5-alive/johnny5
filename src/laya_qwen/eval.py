"""Run a pipeline over the held-out SimpleQA questions, grade, and summarize.

Usage:
  uv run laya-qwen-eval run baseline [--limit N] [--concurrency N] [--name RUN]
  uv run laya-qwen-eval summary RUN
Runs resume: questions already in results/<RUN>/answers.jsonl are skipped.
"""

import argparse
import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import grader, simpleqa
from .pipelines import PIPELINES

RESULTS = simpleqa.ROOT / "results"


def answers_path(run: str) -> Path:
    return RESULTS / run / "answers.jsonl"


def load_rows(run: str) -> list[dict]:
    path = answers_path(run)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_one(pipeline, item: simpleqa.Item) -> dict:
    row = {"id": item.id, "question": item.question, "gold": item.answer, "topic": item.topic}
    try:
        ans = pipeline(item.question)
        row.update(response=ans.text, verified=ans.verified, meta=ans.meta)
        row["grade"] = grader.grade(item.question, item.answer, ans.text)
        if "draft_texts" in ans.meta:  # grade every draft so a grouping replay needs no new GPU time
            row["meta"]["draft_grades"] = [
                grader.grade(item.question, item.answer, t) if t else "not_attempted" for t in ans.meta["draft_texts"]
            ]
    except Exception as e:
        row.update(response=None, verified=None, meta={}, grade="error", error=f"{type(e).__name__}: {e}")
        traceback.print_exc()
    return row


def cmd_run(args) -> None:
    pipeline = PIPELINES[args.pipeline]
    run = args.name or args.pipeline
    path = answers_path(run)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Errored rows are retried on resume.
    done = {r["id"] for r in load_rows(run) if r["grade"] != "error"}
    if args.split == "dev":  # tuning questions: a fixed sample, never the held-out 200
        import random

        pool = random.Random(args.seed).sample(simpleqa.dev(), args.dev_n)
    elif args.split == "tuning":  # stage 4 tuning split: disjoint from held-out and earlier dev samples
        pool = simpleqa.tuning_sample(args.dev_n, args.seed)
    else:
        pool = simpleqa.heldout()
    todo = [it for it in pool if it.id not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"run={run} pipeline={args.pipeline} done={len(done)} todo={len(todo)}", flush=True)

    lock = threading.Lock()
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(run_one, pipeline, it) for it in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            with lock, path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            secs = row["meta"].get("seconds", "-")
            print(f"[{n}/{len(todo)}] {row['grade']:<13} {secs}s  {row['question'][:70]}", flush=True)
    print(f"elapsed {time.monotonic() - start:.0f}s", flush=True)
    summarize(run)


def latest_rows(run: str) -> list[dict]:
    """Last row per id, so retried errors replace the failed attempt."""
    return list({r["id"]: r for r in load_rows(run)}.values())


def metrics(rows: list[dict]) -> dict:
    n = len(rows)
    c = sum(r["grade"] == "correct" for r in rows)
    i = sum(r["grade"] == "incorrect" for r in rows)
    na = sum(r["grade"] == "not_attempted" for r in rows)
    attempted = c + i
    cga = c / attempted if attempted else 0.0
    correct = c / n if n else 0.0
    f = 2 * correct * cga / (correct + cga) if correct + cga else 0.0
    return {
        "n": n,
        "correct": c,
        "incorrect": i,
        "not_attempted": na,
        "other": n - c - i - na,
        "pct_correct": round(100 * correct, 1),
        "pct_incorrect": round(100 * i / n, 1) if n else 0.0,
        "correct_given_attempted": round(100 * cga, 1),
        "f_score": round(100 * f, 1),
    }


def summarize(run: str) -> dict:
    rows = latest_rows(run)
    summary = {"run": run, "overall": metrics(rows)}
    labelled = [r for r in rows if r.get("verified") is not None]
    if labelled:
        summary["verified"] = metrics([r for r in labelled if r["verified"]])
        summary["unverified_guess"] = metrics([r for r in labelled if not r["verified"]])
    secs = [r["meta"]["seconds"] for r in rows if r.get("meta", {}).get("seconds") is not None]
    if secs:
        secs.sort()
        summary["seconds"] = {"mean": round(sum(secs) / len(secs), 1), "p50": secs[len(secs) // 2], "max": secs[-1]}
    (RESULTS / run / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    p = argparse.ArgumentParser(prog="laya-qwen-eval")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("pipeline", choices=sorted(PIPELINES))
    r.add_argument("--name", help="run name (default: pipeline name)")
    r.add_argument("--limit", type=int, help="only run the next N unanswered questions")
    r.add_argument("--concurrency", type=int, default=1, help="parallel questions (match OLLAMA_NUM_PARALLEL)")
    r.add_argument("--split", choices=["heldout", "dev", "tuning"], default="heldout")
    r.add_argument("--dev-n", type=int, default=200, help="sample size (with --split dev or tuning)")
    r.add_argument("--seed", type=int, default=2101, help="sample seed (with --split dev or tuning; use 4060 for tuning)")
    s = sub.add_parser("summary")
    s.add_argument("run")
    args = p.parse_args()
    if args.cmd == "run":
        cmd_run(args)
    else:
        summarize(args.run)


if __name__ == "__main__":
    main()
