"""Stage 7 nightly updater (DESIGN.md stage 7 Q8, Q12, Q13, Q15): staging index only.

One run:
  1. read the enwiki page_change feed from the saved resume point up to the run's start time (namespace 0, plus
     pages moved out of it), keeping the last event per page;
  2. copy the index the staging pointer targets (the pointer target itself is never written);
  3. fetch each changed article's latest HTML (deduplicated, <=3 concurrent, <=190 req/min, project User-Agent),
     parse it with the monthly build's parser and replace the article in the copy; deletions, redirects and moves
     out of namespace 0 remove the article;
  4. run the five Q13 checks on the copy;
  5. on a full pass, switch the wiki-staging.db symlink to the copy (atomic rename) and advance the resume point.
     On any failure: no swap, staging stays on yesterday's copy, resume point unchanged, failure logged.

The live index (wiki.db) is never opened and the answering service is never touched. Every run appends a start
record and a result record to ~/laya-data/stage7-updates/runs.jsonl, the reliability record for the Oct 30 review.

Usage (on argo):
  python -m laya_qwen.wiki_update run [--since ISO_TIME] [--limit N]   # --since only for the first run
  python -m laya_qwen.wiki_update status
"""

import argparse
import fcntl
import json
import os
import random
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path
from urllib.parse import quote

import httpx

from . import wiki_store
from .html_corpus import parse_article
from .retrieval import RetrievalConfig, WikiIndexRetriever

DATA = Path(os.environ.get("LAYA_QWEN_DATA", "~/laya-data")).expanduser()
STAGING = DATA / "wiki-staging.db"
LIVE = DATA / "wiki.db"  # never opened here; size and mtime are recorded to show it is untouched
WORK = DATA / "stage7-updates"
STATE = WORK / "state.json"
RUNS = WORK / "runs.jsonl"
PROBES = Path(os.environ.get("LAYA_QWEN_PROBES", Path(__file__).resolve().parents[2] / "data" / "stage7_probes.json"))

STREAM = "https://stream.wikimedia.org/v2/stream/mediawiki.page_change.v1"
REST = "https://en.wikipedia.org/w/rest.php/v1/page"
USER_AGENT = "laya-qwen/0.1 (https://number5alive.com)"
CONCURRENCY = 3
PER_MINUTE = 190  # under the 200 req/min unauthenticated limit (Q10)
STREAM_MARGIN = timedelta(minutes=2)  # read this far past the cutoff so both datacenter topics have caught up
CANARY_SAMPLE = 50
COMMIT_EVERY = 500

CHECKS = ("map_consistency", "changed_articles_exact", "counts_explained", "probe_questions",
          "changed_articles_findable")


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class Log:
    def __init__(self, path: Path):
        self.f = open(path, "a")

    def __call__(self, msg: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        self.f.write(line + "\n")
        self.f.flush()


def append_run(rec: dict) -> None:
    with open(RUNS, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def file_stamp(p: Path) -> dict | None:
    try:
        st = p.stat()
        return {"size": st.st_size, "mtime": st.st_mtime}
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------- 1. change feed

def read_changes(since: datetime, until: datetime, log: Log) -> tuple[dict, dict]:
    """Last event per enwiki page in [since, until), for namespace 0 and pages moved out of it."""
    pages, stats = {}, {"events_seen": 0, "enwiki_ns0_events": 0, "by_kind": {}, "reconnects": 0}
    position, stop = since, until + STREAM_MARGIN
    deadline = time.monotonic() + 3 * 3600
    while True:
        try:
            with httpx.stream("GET", STREAM, params={"since": iso(position)}, headers={"User-Agent": USER_AGENT},
                              timeout=httpx.Timeout(30, read=90)) as r:
                r.raise_for_status()
                data = []
                for line in r.iter_lines():
                    if line.startswith("data:"):
                        data.append(line[5:].strip())
                        continue
                    if line or not data:
                        continue
                    ev = json.loads("".join(data))
                    data = []
                    stats["events_seen"] += 1
                    meta = ev.get("meta") or {}
                    dt = parse_dt(meta.get("dt", "1970-01-01T00:00:00Z"))
                    if meta.get("domain") == "canary":
                        if dt >= stop:
                            return pages, stats
                        continue
                    if dt >= stop:
                        return pages, stats
                    position = max(position, dt - timedelta(seconds=5))
                    if stats["events_seen"] % 500_000 == 0:
                        log(f"feed: {stats['events_seen']:,} events read, at {iso(dt)}, {len(pages):,} pages")
                    if ev.get("wiki_id") != "enwiki" or dt < since or dt >= until:
                        continue
                    page = ev.get("page") or {}
                    prior_ns = ((ev.get("prior_state") or {}).get("page") or {}).get("namespace_id")
                    ns = page.get("namespace_id")
                    if ns != 0 and prior_ns != 0:
                        continue
                    kind = ev.get("page_change_kind", "edit")
                    stats["enwiki_ns0_events"] += 1
                    stats["by_kind"][kind] = stats["by_kind"].get(kind, 0) + 1
                    pid = str(page.get("page_id"))
                    prev = pages.get(pid)
                    if prev is None or dt >= prev["dt"]:
                        pages[pid] = {"page_id": pid, "key": page.get("page_title", ""), "kind": kind, "ns": ns,
                                      "is_redirect": bool(page.get("is_redirect")), "dt": dt,
                                      "rev_id": (ev.get("revision") or {}).get("rev_id")}
            raise httpx.ReadError("stream ended")
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            stats["reconnects"] += 1
            if time.monotonic() > deadline or stats["reconnects"] > 50:
                raise RuntimeError(f"change feed: gave up after {stats['reconnects']} reconnects ({e})") from e
            log(f"feed: reconnecting from {iso(position)} after {type(e).__name__}: {e}")
            time.sleep(min(60, 5 * stats["reconnects"]))


# ---------------------------------------------------------------- 3. fetch

class RateLimit:
    def __init__(self, per_minute: int):
        self.interval, self.next, self.lock = 60 / per_minute, 0.0, threading.Lock()

    def wait(self) -> None:
        with self.lock:
            t = max(time.monotonic(), self.next)
            self.next = t + self.interval
        time.sleep(max(0.0, t - time.monotonic()))


def fetch(client: httpx.Client, limiter: RateLimit, key: str) -> tuple[str, dict | None]:
    """('ok', page) | ('missing', None) | ('error', {'error': ...}) for the latest revision of one title."""
    url = f"{REST}/{quote(key.replace(' ', '_'), safe='')}/with_html"
    for attempt in range(5):
        limiter.wait()
        try:
            r = client.get(url, params={"redirect": "no"})
        except httpx.HTTPError as e:
            err = f"{type(e).__name__}"
        else:
            if r.status_code == 200:
                return "ok", r.json()
            if r.status_code == 404:
                return "missing", None
            err = f"HTTP {r.status_code}"
            if r.status_code == 429:
                ra = r.headers.get("retry-after", "30")
                time.sleep(min(120, float(ra) if ra.isdigit() else 30))
        time.sleep(2 * 2 ** attempt)
    return "error", {"error": err}


def fetch_and_parse(client, limiter, change: dict) -> dict:
    status, page = fetch(client, limiter, change["key"])
    out = {"change": change, "status": status}
    if status != "ok":
        out["error"] = (page or {}).get("error")
        return out
    html = page.get("html") or ""
    out.update(page_id=str(page["id"]), title=page["title"], url=f"https://en.wikipedia.org/wiki/{page['key']}",
               rev_id=int(page["latest"]["id"]), rev_date=page["latest"]["timestamp"])
    if "mw:PageProp/redirect" in html[:20000]:
        out["status"] = "redirect"
        return out
    try:
        out["passages"] = parse_article(page["title"], html)
    except Exception as e:
        out.update(status="error", error=f"parse: {type(e).__name__}: {e}")
    return out


# ---------------------------------------------------------------- 4. checks

def passages_of(db, page_id: str) -> list[tuple[int, str, str]]:
    return db.execute("SELECT pa.passage_rowid, p.text, p.kind FROM passage_article pa JOIN passages p "
                      "ON p.rowid = pa.passage_rowid WHERE pa.page_id = ? ORDER BY pa.passage_rowid",
                      (page_id,)).fetchall()


def counts(db) -> dict:
    return {"articles": db.execute("SELECT count(*) FROM articles").fetchone()[0],
            "passages": db.execute("SELECT count(*) FROM passages_docsize").fetchone()[0],
            "mapped": db.execute("SELECT count(*) FROM passage_article").fetchone()[0]}


def digest(text: str, kind: str = "") -> bytes:
    return sha1(f"{kind}\x00{text}".encode()).digest()


def check_exact(db, applied: dict, deleted: set) -> dict:
    """Q13 check 2: each changed article's passages equal its new parse (text and kind, in order); deleted articles
    are gone. applied: page_id -> digests of the parsed passages."""
    bad = []
    for pid, expected in applied.items():
        got = [digest(t, k) for _, t, k in passages_of(db, pid)]
        if got != expected:
            bad.append(pid)
    for pid in deleted:
        if db.execute("SELECT 1 FROM articles WHERE page_id = ?", (pid,)).fetchone() or passages_of(db, pid):
            bad.append(pid)
    return {"ok": not bad, "articles_checked": len(applied), "deletions_checked": len(deleted),
            "mismatched": len(bad), "examples": bad[:10]}


def check_counts(before: dict, after: dict, expected: dict) -> dict:
    """Q13 check 3: article and passage counts moved exactly as the applied changes explain."""
    moved = {k: after[k] - before[k] for k in before}
    ok = (moved["articles"] == expected["articles"] and moved["passages"] == expected["passages"]
          and moved["mapped"] == expected["passages"])
    return {"ok": ok, "before": before, "after": after, "moved": moved, "explained": expected}


def load_probes() -> list[dict]:
    return json.loads(PROBES.read_text())


def run_probes(db_path: Path) -> dict:
    """Q13 check 4: fixed probe questions with answers in stable articles still retrieve them.

    Uses the adopted retriever's keyword stage (normalized FTS query + title-matched articles), not the
    nomic-embed-text re-rank, so the nightly job never touches the GPU."""
    r = WikiIndexRetriever(db_path, "staging-copy", RetrievalConfig(normalize_query=True, expand_titles=True))
    failed = []
    probes = load_probes()
    for p in probes:
        cands = r.keyword_search(p["q"])
        cands += r._add_articles(cands, r.title_matches(p["q"]))
        if not any(c.title == p["title"] and p["answer"].lower() in c.text.lower() for c in cands):
            failed.append(p["q"])
    return {"ok": not failed, "probes": len(probes), "failed": failed}


def phrase(text: str, n: int = 8) -> str | None:
    """A distinctive n-token phrase from a passage: the window with the most long, distinct tokens."""
    toks = re.findall(r"[^\W_]+", text)
    if len(toks) < n:
        return None
    best = max(range(len(toks) - n + 1),
               key=lambda i: (len({t.lower() for t in toks[i:i + n] if len(t) > 3}), -abs(i - len(toks) // 2)))
    return " ".join(toks[best:best + n])


def check_findable(db, new_passages: dict, seed: str) -> dict:
    """Q13 check 5: sampled changed articles' new passages are present and found by the copy's FTS index.
    new_passages: page_id -> digests of passages whose text was not in the article before."""
    rng = random.Random(seed)
    pids = sorted(new_passages)
    sample = rng.sample(pids, min(CANARY_SAMPLE, len(pids)))
    failed, checked = [], 0
    for pid in sample:
        want = rng.choice(new_passages[pid])
        rows = [(r, t) for r, t, _ in passages_of(db, pid) if digest(t) == want]
        text = rows[0][1] if rows else ""
        ph = phrase(text)
        if not rows:
            failed.append({"page_id": pid, "why": "passage not present"})
            continue
        checked += 1
        if ph is None:
            continue  # too short for a phrase; presence verified above
        # Ask the FTS index whether the phrase matches this passage's rowid. (A ranked "MATCH ... LIMIT n" scan gave a
        # false failure on 2026-10-19: a table-header phrase matched 190,042 passages and the sampled one ranked past
        # the limit, though it was indexed.)
        found = any(db.execute("SELECT 1 FROM passages WHERE passages MATCH ? AND rowid = ?",
                               (f'text : "{ph}"', r)).fetchone() for r, _ in rows)
        if not found:
            failed.append({"page_id": pid, "why": "not found by FTS", "phrase": ph})
    return {"ok": not failed and (len(sample) > 0 or not pids), "sampled": len(sample), "checked": checked,
            "failed": failed[:10], "articles_with_new_passages": len(pids)}


# ---------------------------------------------------------------- run

def prune(keep: set[Path], log: Log) -> None:
    """Remove staging copies other than the current target and its rollback (never the monthly base build)."""
    for p in DATA.glob("wiki-staging-*.db"):
        if p.resolve() not in keep:
            for q in (p, Path(f"{p}-wal"), Path(f"{p}-shm")):
                q.unlink(missing_ok=True)
            log(f"removed old staging copy {p.name}")


def run(since_arg: str | None, limit: int | None) -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    lock = open(WORK / "update.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another update run holds the lock", file=sys.stderr)
        append_run({"run_id": now().strftime("%Y%m%d-%H%M%S"), "started": iso(now()), "status": "skipped_locked",
                    "finished": iso(now()), "swapped": False})
        return 2
    started = now()
    run_id = started.strftime("%Y%m%d-%H%M%S")
    log = Log(WORK / f"run-{run_id}.log")
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    live_before = file_stamp(LIVE)
    rec = {"run_id": run_id, "started": iso(started), "status": "started"}
    append_run(rec)
    t0, phases = time.monotonic(), {}
    copy_path, swapped = None, False
    try:
        source = STAGING.resolve(strict=True)
        if source == LIVE.resolve():
            raise RuntimeError("staging pointer resolves to the live index; refusing")
        since = parse_dt(since_arg) if since_arg else parse_dt(state["position"]) if "position" in state else None
        if since is None:
            raise RuntimeError("no saved resume point; first run needs --since")
        until = started
        rec.update(window={"since": iso(since), "until": iso(until)}, source=source.name)
        prune({source, Path(state["rollback"]).resolve() if state.get("rollback") else source}, log)

        # 1. feed
        t = time.monotonic()
        log(f"reading change feed {iso(since)} .. {iso(until)}")
        pages, feed = read_changes(since, until, log)
        for p in state.get("pending", []):  # fetch failures carried over from the previous run
            pages.setdefault(p["page_id"], {**p, "dt": since})
        phases["feed_s"] = round(time.monotonic() - t)
        changes = list(pages.values())[:limit] if limit else list(pages.values())
        removals = [c for c in changes if c["kind"] == "delete" or c["ns"] != 0]
        fetches = [c for c in changes if not (c["kind"] == "delete" or c["ns"] != 0)]
        rec["feed"] = feed | {"pages_changed": len(changes), "to_fetch": len(fetches), "to_remove": len(removals),
                              "carried_over": len(state.get("pending", []))}
        log(f"feed: {feed['enwiki_ns0_events']:,} enwiki ns0 events, {len(changes):,} pages "
            f"({len(fetches):,} to fetch, {len(removals):,} to remove)")

        # 2. copy
        t = time.monotonic()
        wal = Path(f"{source}-wal")
        if wal.exists() and wal.stat().st_size:
            raise RuntimeError(f"{wal.name} is not empty; source index is not self-contained")
        need = source.stat().st_size * 1.1 + 20e9
        if shutil.disk_usage(DATA).free < need:
            raise RuntimeError(f"not enough disk for the copy (need {need / 1e9:.0f} GB)")
        copy_path = DATA / f"wiki-staging-{run_id}.db"
        log(f"copying {source.name} -> {copy_path.name}")
        shutil.copyfile(source, copy_path)
        phases["copy_s"] = round(time.monotonic() - t)

        db = wiki_store.connect(copy_path)
        db.executescript("PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;")
        before = counts(db)

        # 3. fetch, parse, apply
        t = time.monotonic()
        applied, new_passages, deleted, pending = {}, {}, set(), []
        tally = {k: 0 for k in ("applied", "created", "unchanged", "removed", "redirects_removed", "missing",
                                "mismatched", "fetch_errors", "not_in_index")}
        expected = {"articles": 0, "passages": 0}
        pass_in = pass_out = 0

        def remove(pid: str, why: str) -> None:
            nonlocal pass_out
            n = db.execute("SELECT n_passages FROM articles WHERE page_id = ?", (pid,)).fetchone()
            if n is None:
                tally["not_in_index"] += 1
                return
            wiki_store.delete_article(db, pid)
            pass_out += n[0]
            expected["articles"] -= 1
            expected["passages"] -= n[0]
            deleted.add(pid)
            tally[why] += 1

        for c in removals:
            remove(c["page_id"], "removed")
        db.commit()

        limiter = RateLimit(PER_MINUTE)
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=False) as client, \
                ThreadPoolExecutor(CONCURRENCY) as pool:
            futures = [pool.submit(fetch_and_parse, client, limiter, c) for c in fetches]
            for n, fut in enumerate(as_completed(futures), 1):
                res = fut.result()
                c, status = res["change"], res["status"]
                if status == "missing":
                    tally["missing"] += 1
                elif status == "error":
                    if (res.get("error") or "").startswith("parse:"):
                        log(f"{c['key']}: {res['error']}")
                    tally["fetch_errors"] += 1
                    pending.append({k: c[k] for k in ("page_id", "key", "kind", "ns", "is_redirect")})
                elif res["page_id"] != c["page_id"]:
                    tally["mismatched"] += 1  # the title now belongs to another page; that page has its own events
                elif status == "redirect":
                    remove(c["page_id"], "redirects_removed")
                else:
                    pid = c["page_id"]
                    old = db.execute("SELECT rev_id, n_passages FROM articles WHERE page_id = ?", (pid,)).fetchone()
                    old_texts = {digest(t) for _, t, _ in passages_of(db, pid)} if old else set()
                    force = c["kind"] == "visibility_change"
                    if wiki_store.replace_article(db, pid, res["title"], res["url"], res["rev_id"], res["rev_date"],
                                                  res["passages"], only_if_newer=not force):
                        ps = res["passages"]
                        tally["applied"] += 1
                        tally["created"] += old is None
                        deleted.discard(pid)
                        applied[pid] = [digest(p.text, p.kind) for p in ps]
                        fresh = [d for d in (digest(p.text) for p in ps) if d not in old_texts]
                        if fresh:
                            new_passages[pid] = fresh
                        pass_in += len(ps)
                        pass_out += old[1] if old else 0
                        expected["articles"] += old is None
                        expected["passages"] += len(ps) - (old[1] if old else 0)
                    else:
                        tally["unchanged"] += 1
                if n % COMMIT_EVERY == 0:
                    db.commit()
                    rate = n / max(1, time.monotonic() - t) * 60
                    log(f"fetch: {n:,}/{len(fetches):,} ({rate:.0f}/min) {json.dumps(tally)}")
        db.commit()
        phases["fetch_apply_s"] = round(time.monotonic() - t)
        rec["articles"] = tally | {"fetched": len(fetches)}
        rec["passages"] = {"in": pass_in, "out": pass_out}
        log(f"applied: {json.dumps(tally)}; passages in {pass_in:,}, out {pass_out:,}")

        # 4. checks
        t = time.monotonic()
        checks = {}
        log("check 1: map consistency")
        checks["map_consistency"] = wiki_store.consistency(db)
        log("check 2: changed articles exact")
        checks["changed_articles_exact"] = check_exact(db, applied, deleted)
        log("check 3: counts explained")
        checks["counts_explained"] = check_counts(before, counts(db), expected)
        log("check 4: probe questions")
        checks["probe_questions"] = run_probes(copy_path)
        log("check 5: changed articles findable")
        checks["changed_articles_findable"] = check_findable(db, new_passages, run_id)
        phases["checks_s"] = round(time.monotonic() - t)
        rec["checks"] = {name: checks[name] for name in CHECKS}
        passed = all(checks[name]["ok"] for name in CHECKS)
        for name in CHECKS:
            log(f"  {name}: {'PASS' if checks[name]['ok'] else 'FAIL'}")

        status = "applied" if passed else "failed_checks"
        db.execute("INSERT OR REPLACE INTO update_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (run_id, iso(started), iso(now()), status, iso(until), tally["applied"], len(deleted),
                    json.dumps({"checks": {k: v["ok"] for k, v in checks.items()}, "source": source.name})))
        if passed:
            wiki_store.set_meta(db, last_update_run=run_id, last_update_position=iso(until),
                                update_stream_start=state.get("stream_start", iso(since)))
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.close()

        # 5. swap (test runs with --limit never swap or move the resume point)
        if passed and limit:
            status = rec["status"] = "test_passed"
            log("test run passed all checks; no swap (--limit)")
        elif passed:
            tmp = DATA / ".wiki-staging.db.new"
            tmp.unlink(missing_ok=True)
            tmp.symlink_to(copy_path)
            os.replace(tmp, STAGING)
            swapped = True
            state.update(position=iso(until), rollback=str(source), current=str(copy_path), pending=pending,
                         stream_start=state.get("stream_start", iso(since)), last_applied_run=run_id)
            STATE.write_text(json.dumps(state, indent=1))
            log(f"swapped: wiki-staging.db -> {copy_path.name} (rollback {source.name})")
            prune({copy_path.resolve(), source}, log)
        else:
            log("checks failed: no swap; staging stays on " + source.name)
        rec["status"] = status
        if limit and copy_path:
            for q in (copy_path, Path(f"{copy_path}-wal"), Path(f"{copy_path}-shm")):
                q.unlink(missing_ok=True)
            log(f"test run: removed {copy_path.name}")
    except Exception as e:
        rec.update(status="error", error=f"{type(e).__name__}: {e}")
        log(f"ERROR {type(e).__name__}: {e}")
    finally:
        rec.update(finished=iso(now()), duration_s=round(time.monotonic() - t0), phases=phases, swapped=swapped,
                   staging_target=STAGING.resolve().name if STAGING.exists() else None,
                   copy=copy_path.name if copy_path else None,
                   live_index_untouched=file_stamp(LIVE) == live_before, live_index=live_before)
        append_run(rec)
        log(f"run {run_id}: {rec['status']} in {rec['duration_s']} s")
    return 0 if rec["status"] in ("applied", "test_passed") else 1


def status() -> None:
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    print(json.dumps({"staging_target": STAGING.resolve().name, "state": {k: v for k, v in state.items()
                                                                          if k != "pending"},
                      "pending": len(state.get("pending", []))}, indent=1))
    if RUNS.exists():
        for line in RUNS.read_text().splitlines()[-6:]:
            r = json.loads(line)
            print(r["run_id"], r["status"], r.get("duration_s"), r.get("window"),
                  {k: v["ok"] for k, v in (r.get("checks") or {}).items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--since", help="ISO time to start the feed from (first run only)")
    r.add_argument("--limit", type=int, help="process at most N changed pages (testing)")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "status":
        status()
    else:
        sys.exit(run(a.since, a.limit))
