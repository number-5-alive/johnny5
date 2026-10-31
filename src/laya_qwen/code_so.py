"""Code shelf, Q&A half: Stack Exchange data dump (Posts.7z) to an FTS5 index, one passage per question.

A passage holds the question (title and body), its accepted answer and up to two more answers by score. HTML is
converted with code blocks kept as indented plain text (code_text). Metadata carries the agreement signal (question
and answer scores, accepted flag) and CC BY-SA attribution (author, post URLs, dates, licence).

Three streaming passes over `7z x -so Posts.7z`, so no decompressed XML is stored:
  scan     per-row ids, scores, parents, body lengths -> scan.npz (sizes are projected from it before building)
  extract  the selected questions and answers, HTML -> text in worker processes, into 64 bucket files by question id
  build    bucket by bucket: assemble passages, insert into the FTS index; author names from Users.7z

Usage (on argo, files on the hub):
  python -m laya_qwen.code_so scan    DUMP_DIR SITE WORK_DIR
  python -m laya_qwen.code_so project WORK_DIR
  python -m laya_qwen.code_so extract DUMP_DIR SITE WORK_DIR [--min-q-score N] [--require-answer]
  python -m laya_qwen.code_so build   DUMP_DIR SITE WORK_DIR OUT.db --vintage YYYY-MM-DD
"""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from array import array
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from .code_text import html_to_text

BUCKETS = 128
QUIET = ((2, 30), (3, 30))  # no parse/index bursts while the 03:00 CT staging update copies the wiki index
ATTR = re.compile(r'(\w+)="([^"]*)"')
SITE_URLS = {"stackoverflow.com": "https://stackoverflow.com"}
MAX_ANSWERS = 3  # accepted + up to two more by score


def quiet_window_wait() -> None:
    """Sleep through 02:30-03:30 America/Chicago."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    while True:
        t = datetime.now(ZoneInfo("America/Chicago"))
        if not (QUIET[0] <= (t.hour, t.minute) < QUIET[1]):
            return
        print(f"quiet window ({t:%H:%M} CT): pausing", flush=True)
        time.sleep(120)


def site_url(site: str) -> str:
    return SITE_URLS.get(site, f"https://{site}")


def posts_file(dump: Path, site: str) -> Path:
    for name in (f"{site}-Posts.7z", f"{site}.7z"):
        if (dump / name).exists():
            return dump / name
    raise FileNotFoundError(f"no Posts archive for {site} in {dump}")


def stream_rows(archive: Path, member: str = "Posts.xml"):
    """Lines of one XML member of a .7z, streamed through 7z (no extraction to disk)."""
    p = subprocess.Popen(["7z", "x", "-so", str(archive), member], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, bufsize=1 << 20)
    try:
        for raw in p.stdout:
            if raw.startswith(b"  <row "):
                yield raw.decode("utf-8")
    finally:
        p.stdout.close()
        p.wait()


# ---------------------------------------------------------------- scan

def scan(dump: Path, site: str, work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    q = {k: array("q") for k in ("id", "accepted", "score", "blen", "closed")}
    a = {k: array("q") for k in ("id", "parent", "score", "blen")}
    t0, n, last_id, unordered = time.time(), 0, 0, 0
    for line in stream_rows(posts_file(dump, site)):
        n += 1
        b = line.find(' Body="')
        head = dict(ATTR.findall(line[:b if b > 0 else 400]))
        pid = int(head["Id"])
        unordered += pid < last_id
        last_id = pid
        blen = line.find('"', b + 7) - (b + 7) if b > 0 else 0
        kind = head.get("PostTypeId")
        if kind == "1":
            q["id"].append(pid)
            q["accepted"].append(int(head.get("AcceptedAnswerId", 0)))
            q["score"].append(int(head.get("Score", 0)))
            q["blen"].append(blen + len(re.search(r' Title="([^"]*)"', line).group(1)) if ' Title="' in line else blen)
            q["closed"].append(1 if ' ClosedDate="' in line else 0)
        elif kind == "2":
            a["id"].append(pid)
            a["parent"].append(int(head.get("ParentId", 0)))
            a["score"].append(int(head.get("Score", 0)))
            a["blen"].append(blen)
        if n % 2_000_000 == 0:
            print(f"scan: {n:,} rows ({len(q['id']):,} questions, {len(a['id']):,} answers) "
                  f"{time.time() - t0:.0f}s", flush=True)
    np.savez(work / "scan.npz", **{f"q_{k}": np.frombuffer(v, dtype=np.int64) for k, v in q.items()},
             **{f"a_{k}": np.frombuffer(v, dtype=np.int64) for k, v in a.items()})
    info = {"rows": n, "questions": len(q["id"]), "answers": len(a["id"]), "unordered_ids": unordered,
            "seconds": round(time.time() - t0)}
    (work / "scan.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info), flush=True)


def select(work: Path, min_q_score: int | None, require_answer: bool):
    """Question ids kept and, per kept question, its accepted answer plus up to two more answers by score."""
    s = np.load(work / "scan.npz")
    qid, acc, qscore = s["q_id"], s["q_accepted"], s["q_score"]
    aid, apar, ascore = s["a_id"], s["a_parent"], s["a_score"]
    # rank answers within each question: accepted first, then score desc, then older first
    is_acc = np.isin(aid, acc[acc > 0])
    order = np.lexsort((aid, -ascore, ~is_acc, apar))
    apar_o, aid_o = apar[order], aid[order]
    first = np.r_[True, apar_o[1:] != apar_o[:-1]]
    grp_start = np.maximum.accumulate(np.where(first, np.arange(len(apar_o)), 0))
    rank = np.arange(len(apar_o)) - grp_start
    keep_a = rank < MAX_ANSWERS
    sel_a, sel_par = aid_o[keep_a], apar_o[keep_a]
    has_answer = np.isin(qid, sel_par)
    keep_q = np.ones(len(qid), dtype=bool)
    if min_q_score is not None:
        keep_q &= qscore >= min_q_score
    if require_answer:
        keep_q &= has_answer
    kept_q = qid[keep_q]
    in_kept = np.isin(sel_par, kept_q)
    return kept_q, sel_a[in_kept], s, keep_q, order[keep_a][in_kept]


def project(work: Path) -> None:
    """Projected passage text and index size for candidate filters (HTML length x 0.8 ~ text; index ~1.7 x text)."""
    s = np.load(work / "scan.npz")
    print(json.dumps(json.loads((work / "scan.json").read_text())))
    for label, mqs, req in (("all questions", None, False), ("questions with an answer", None, True),
                            ("score >= 0, with an answer", 0, True), ("score >= 1, with an answer", 1, True),
                            ("score >= 2, with an answer", 2, True), ("score >= 5, with an answer", 5, True)):
        kept_q, sel_a, _, keep_q, a_idx = select(work, mqs, req)
        html = s["q_blen"][keep_q].sum() + s["a_blen"][a_idx].sum()
        text_gb = html * 0.8 / 1e9
        print(f"{label:32s} questions {len(kept_q):>11,}  answers {len(sel_a):>11,}  "
              f"text ~{text_gb:6.1f} GB  index ~{text_gb * 1.7:6.1f} GB", flush=True)


# ---------------------------------------------------------------- extract

def _convert(batch: list[str]) -> list[tuple[int, str]]:
    out = []
    for line in batch:
        el = ElementTree.fromstring(line)
        r = el.attrib
        kind = r.get("PostTypeId")
        rec = {"id": int(r["Id"]), "score": int(r.get("Score", 0)), "created": r.get("CreationDate"),
               "owner_id": int(r["OwnerUserId"]) if r.get("OwnerUserId", "").lstrip("-").isdigit() else None,
               "owner_name": r.get("OwnerDisplayName"), "license": r.get("ContentLicense"),
               "text": html_to_text(r.get("Body", ""))}
        if kind == "1":
            rec.update(kind="q", title=r.get("Title", ""), tags=[t for t in re.split(r"[|<>]", r.get("Tags", "")) if t],
                       accepted=int(r.get("AcceptedAnswerId", 0)) or None, closed=r.get("ClosedDate"),
                       answer_count=int(r.get("AnswerCount", 0)))
            qid = rec["id"]
        else:
            rec.update(kind="a", parent=int(r["ParentId"]))
            qid = rec["parent"]
        out.append((qid, json.dumps(rec, ensure_ascii=False)))
    return out


def extract(dump: Path, site: str, work: Path, min_q_score: int | None, require_answer: bool,
            workers: int = 12) -> None:
    kept_q, sel_a, _, _, _ = select(work, min_q_score, require_answer)
    wanted = np.union1d(kept_q, sel_a)
    (work / "selection.json").write_text(json.dumps({"min_q_score": min_q_score, "require_answer": require_answer,
                                                     "questions": int(len(kept_q)), "answers": int(len(sel_a))}))
    bdir = work / "buckets"
    bdir.mkdir(exist_ok=True)
    files = [open(bdir / f"{i:02d}.jsonl", "w", encoding="utf-8") for i in range(BUCKETS)]
    t0, n, batch, pending = time.time(), 0, [], []  # Posts.xml is not in Id order (scan: unordered_ids)

    def drain(block: bool):
        while pending and (block or pending[0].done()):
            for qid, js in pending.pop(0).result():
                files[qid % BUCKETS].write(js + "\n")

    with ProcessPoolExecutor(workers) as pool:
        for line in stream_rows(posts_file(dump, site)):
            pid = int(line[line.find('Id="') + 4:line.find('"', line.find('Id="') + 4)])
            i = int(np.searchsorted(wanted, pid))
            if i >= len(wanted) or wanted[i] != pid:
                continue
            n += 1
            batch.append(line)
            if len(batch) == 2000:
                if n % 200_000 < 2000:
                    quiet_window_wait()
                pending.append(pool.submit(_convert, batch))
                batch = []
                drain(len(pending) > workers * 3)
            if n % 1_000_000 == 0:
                print(f"extract: {n:,}/{len(wanted):,} posts ({time.time() - t0:.0f}s)", flush=True)
        if batch:
            pending.append(pool.submit(_convert, batch))
        drain(True)
    for f in files:
        f.close()
    print(f"extract done: {n:,} posts in {time.time() - t0:.0f}s", flush=True)


# ---------------------------------------------------------------- build

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
    title, url UNINDEXED, text, tags, source UNINDEXED, tokenize = 'porter unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS passage_meta (passage_rowid INTEGER PRIMARY KEY, doc TEXT, vintage TEXT, meta TEXT);
CREATE TABLE IF NOT EXISTS sources (source TEXT PRIMARY KEY, kind TEXT, vintage TEXT, detail TEXT, built_at TEXT,
                                    passages INTEGER);
"""


def users(dump: Path, site: str, need: set[int]) -> dict[int, str]:
    arch = dump / f"{site}-Users.7z" if (dump / f"{site}-Users.7z").exists() else posts_file(dump, site)
    out = {}
    for line in stream_rows(arch, "Users.xml"):
        m = re.search(r' Id="(-?\d+)"', line)
        uid = int(m.group(1)) if m else None
        if uid in need:
            name = re.search(r' DisplayName="([^"]*)"', line)
            out[uid] = ElementTree.fromstring(f'<x n="{name.group(1)}"/>').attrib["n"] if name else ""
    return out


def passage(q: dict, answers: list[dict], base: str, names: dict) -> tuple[str, str, str, str, dict]:
    def who(p):
        return p.get("owner_name") or names.get(p.get("owner_id")) or None

    url = f"{base}/questions/{q['id']}"
    parts = [q["title"], "", q["text"]]
    meta_answers = []
    for a in answers:
        label = "Accepted answer" if a["id"] == q.get("accepted") else "Answer"
        parts += ["", f"{label} (score {a['score']}):", "", a["text"]]
        meta_answers.append({"id": a["id"], "score": a["score"], "accepted": a["id"] == q.get("accepted"),
                             "created": a["created"], "author": who(a), "author_id": a.get("owner_id"),
                             "url": f"{base}/a/{a['id']}", "license": a.get("license")})
    meta = {"question_id": q["id"], "title": q["title"], "tags": q["tags"], "question_score": q["score"],
            "question_created": q["created"], "question_author": who(q), "question_author_id": q.get("owner_id"),
            "answer_count": q.get("answer_count"), "has_accepted": bool(q.get("accepted")),
            "accepted_included": any(m["accepted"] for m in meta_answers), "closed": q.get("closed"),
            "answers": meta_answers, "url": url, "license": q.get("license")}
    return q["title"], url, "\n".join(parts).strip(), " ".join(q["tags"]), meta


def build(dump: Path, site: str, work: Path, out: Path, vintage: str, min_q_score: int | None = None,
          require_answer: bool = False) -> None:
    bdir = work / "buckets"
    need = set()
    for f in sorted(bdir.glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                uid = json.loads(line).get("owner_id")
                if uid is not None:
                    need.add(uid)
    t0 = time.time()
    names = users(dump, site, need)
    print(f"authors: {len(names):,} of {len(need):,} referenced users named ({time.time() - t0:.0f}s)", flush=True)
    db = sqlite3.connect(out)
    db.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF; PRAGMA cache_size = -2000000;" + SCHEMA)
    source = f"so:{site}"
    base = site_url(site)
    total = 0
    skipped = 0
    for f in sorted(bdir.glob("*.jsonl")):
        quiet_window_wait()
        qs, ans = {}, {}
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r["kind"] == "q":
                    qs[r["id"]] = r
                else:
                    ans.setdefault(r["parent"], []).append(r)
        rows = []
        for qid in sorted(qs):
            q = qs[qid]
            if (min_q_score is not None and q["score"] < min_q_score) or (require_answer and qid not in ans):
                skipped += 1
                continue
            al = sorted(ans.get(qid, []), key=lambda a: (a["id"] != q.get("accepted"), -a["score"], a["id"]))
            rows.append(passage(q, al[:MAX_ANSWERS], base, names))
        with db:
            for title, url, text, tags, meta in rows:
                cur = db.execute("INSERT INTO passages (title, url, text, tags, source) VALUES (?, ?, ?, ?, ?)",
                                 (title, url, text, tags, source))
                db.execute("INSERT INTO passage_meta VALUES (?, ?, ?, ?)",
                           (cur.lastrowid, f"{site}/q/{meta['question_id']}", vintage, json.dumps(meta)))
        total += len(rows)
        print(f"build: {f.name} {len(rows):,} passages, total {total:,}, skipped by filter {skipped:,} "
              f"({time.time() - t0:.0f}s)", flush=True)
    sel = {"min_q_score": min_q_score, "require_answer": require_answer, "passages": total,
           "questions_skipped_by_filter": skipped}
    db.execute("INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?)",
               (source, "stackexchange", vintage, json.dumps({"site": site, "dump": str(dump), "selection": sel}),
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), total))
    db.commit()
    print("optimizing...", flush=True)
    db.execute("INSERT INTO passages(passages) VALUES ('optimize')")
    db.commit()
    print(f"BUILD_DONE {total:,} passages ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "extract", "build"):
        p = sub.add_parser(name)
        p.add_argument("dump", type=Path)
        p.add_argument("site")
        p.add_argument("work", type=Path)
        if name == "extract":
            p.add_argument("--min-q-score", type=int)
            p.add_argument("--require-answer", action="store_true")
            p.add_argument("--workers", type=int, default=12)
        if name == "build":
            p.add_argument("out", type=Path)
            p.add_argument("--vintage", required=True)
            p.add_argument("--min-q-score", type=int)
            p.add_argument("--require-answer", action="store_true")
    p = sub.add_parser("project")
    p.add_argument("work", type=Path)
    a = ap.parse_args()
    if a.cmd == "scan":
        scan(a.dump, a.site, a.work)
    elif a.cmd == "project":
        project(a.work)
    elif a.cmd == "extract":
        extract(a.dump, a.site, a.work, a.min_q_score, a.require_answer, a.workers)
    else:
        build(a.dump, a.site, a.work, a.out, a.vintage, a.min_q_score, a.require_answer)
