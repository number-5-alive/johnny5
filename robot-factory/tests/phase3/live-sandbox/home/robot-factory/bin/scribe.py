#!/usr/bin/env python3
"""Robot Factory scribe v1 (Phase 3, task 009, 2026-10-31). Draft for Dan's review.

    python3 bin/scribe.py <task> [--force]

Assembles records/<task>-record.md from what already exists:
  done/<task>.md, logs/<task>*.log, the metas the ledger points at,
  work/<prefix>-* deliverables, and the task's lines in ledger.jsonl.

Seven parts: 1 Commission (the task file, verbatim), 2 What ran (from the
ledger and metas), 3 Deliverables (files, sizes, sha256; the seat's report
from its log), 4 Ledger (the task's lines, verbatim), 5 Pass marks and
moderator review (PENDING MODERATOR REVIEW), 6 Scribe's note (one paragraph,
drafted by the local seat through seats/qwen_local.sh, attributed), 7 the
footer "A record, not an endorsement. The scribe holds no vote."

Writes ONLY under records/ (the record; records/logs/ for the note's prompt,
reply, meta and the scribe's own ledger, records/logs/scribe-ledger.jsonl).
It never writes done/, queue/, working/, work/, logs/, ledger.jsonl or any
task file: every write goes through inside_records(), which refuses anything
whose real path is not under records/.

Exit: 0 record written | 2 refused (bad task name, no done/ file, record
exists without --force) | 3 record written but the note was NOT drafted (the
record says so) | 4 ledger.jsonl or a task line did not parse (nothing written).
"""
import datetime, hashlib, json, os, re, subprocess, sys

BASE = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
RECORDS = os.path.join(BASE, "records")
RLOGS = os.path.join(RECORDS, "logs")
FOOTER = "A record, not an endorsement. The scribe holds no vote."
PENDING = "PENDING MODERATOR REVIEW"


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def die(code, why):
    print("scribe: " + why, file=sys.stderr)
    sys.exit(code)


def inside_records(path):
    """The only gate to the disk. Real path must sit under records/."""
    root = os.path.realpath(RECORDS)
    if not root.startswith(BASE + os.sep) or os.path.islink(RECORDS):
        die(2, "records/ is not a plain directory inside the factory; refusing")
    rp = os.path.realpath(path)
    if not rp.startswith(root + os.sep) or os.path.islink(path):
        die(2, "refusing to write outside records/: %s" % path)
    return rp


def write(path, text):
    rp = inside_records(path)
    tmp = rp + ".tmp"
    inside_records(tmp)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, rp)


def append(path, line):
    with open(inside_records(path), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def fence(text, lang=""):
    """A fence longer than any backtick run inside, so verbatim stays verbatim."""
    n = max([3] + [len(r) + 1 for r in re.findall(r"`{3,}", text)])
    body = text if text.endswith("\n") else text + "\n"
    return "`" * n + lang + "\n" + body + "`" * n + "\n"


def rel(p):
    return os.path.relpath(p, BASE)


def main(argv):
    args = [a for a in argv if a != "--force"]
    force = "--force" in argv
    if len(args) != 1 or not re.fullmatch(r"[0-9]{3}[-a-z0-9]*", args[0]):
        die(2, "usage: scribe.py <task> [--force]   (task like 008-maps-gate-pack)")
    task = args[0]
    prefix = task.split("-")[0]
    done = os.path.join(BASE, "done", task + ".md")
    if not os.path.isfile(done):
        die(2, "no done/%s.md: the scribe records finished tasks only" % task)
    out = os.path.join(RECORDS, task + "-record.md")
    if os.path.exists(out) and not force:
        die(2, "%s exists; the scribe does not overwrite a record without --force" % rel(out))

    # --- the ledger: the task's raw lines, kept byte-for-byte ---
    raw = []
    try:
        with open(os.path.join(BASE, "ledger.jsonl"), encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                s = line.rstrip("\n")
                if not s.strip():
                    continue
                try:
                    j = json.loads(s)
                except ValueError:
                    die(4, "ledger.jsonl line %d did not parse; the record would be incomplete" % n)
                if isinstance(j, dict) and j.get("round") == task:
                    raw.append((s, j))
    except OSError as e:
        die(4, "ledger.jsonl unreadable: %s" % e)

    commission = read(done)
    planned = [j for _, j in raw if j.get("phase") == "planned"]
    actuals = {j.get("call_id"): j for _, j in raw if j.get("phase") == "actual"}

    # --- 2 What ran ---
    ran = []
    total = 0.0
    for i, p in enumerate(planned, 1):
        a = actuals.get(p.get("call_id"))
        ran.append("### Attempt %d: `%s`\n" % (i, p.get("call_id")))
        ran.append("- Planned %s on seat `%s`: worst case $%.2f, output cap %s tokens%s."
                   % (p.get("t"), p.get("seat"), p.get("worst_usd") or 0.0, p.get("max_out_tokens"),
                      ", approval %s" % p["approval"] if p.get("approval") else ""))
        if not a:
            ran.append("- **No actual line in the ledger for this call_id** (open or lost).\n")
            continue
        total += a.get("cost_usd") or 0.0
        ran.append("- Ran to %s: exit `%s`, model `%s`, %s in / %s out tokens, cost $%.4f (%s)%s."
                   % (a.get("t"), a.get("exit"), a.get("model"), a.get("in_tokens"), a.get("out_tokens"),
                      a.get("cost_usd") or 0.0, a.get("cost_source"),
                      ", **input cap exceeded**" if a.get("cap_exceeded") else ""))
        mp = os.path.join(BASE, a.get("meta") or "")
        if a.get("meta") and os.path.isfile(mp):
            try:
                m = json.loads(read(mp))
                ran.append("- Meta `%s`: started %s, finished %s, exit `%s`."
                           % (a["meta"], m.get("started"), m.get("finished"), m.get("exit")))
                diffs = [k for k in ("in_tokens", "out_tokens", "cost_usd", "model")
                         if k in m and m.get(k) != a.get(k)]
                if diffs:
                    ran.append("- **Meta and ledger disagree on: %s.** The ledger is quoted as written."
                               % ", ".join(diffs))
            except ValueError:
                ran.append("- Meta `%s` did not parse." % a["meta"])
        else:
            ran.append("- Meta `%s` not found." % a.get("meta"))
        ran.append("")
    orphans = [c for c in actuals if c not in {p.get("call_id") for p in planned}]
    for c in orphans:
        ran.append("- **Actual line with no planned line:** `%s`" % c)
    ran.append("Attempts: %d. Total recorded cost: $%.4f." % (len(planned), total))
    logs = sorted(f for f in os.listdir(os.path.join(BASE, "logs"))
                  if f.endswith(".log") and (f == task + ".log" or f.startswith(task + ".")))
    ran.append("Logs: " + (", ".join("`logs/%s`" % f for f in logs) or "none found") + ".")

    # --- 3 Deliverables ---
    wdir = os.path.join(BASE, "work")
    files = sorted(f for f in os.listdir(wdir)
                   if f.startswith(prefix + "-") and os.path.isfile(os.path.join(wdir, f)))
    deliv = ["| File | Bytes | sha256 |", "|---|---|---|"]
    for f in files:
        b = open(os.path.join(wdir, f), "rb").read()
        deliv.append("| `work/%s` | %d | `%s` |" % (f, len(b), hashlib.sha256(b).hexdigest()))
    if not files:
        deliv = ["No files matching `work/%s-*`." % prefix]
    report = read(os.path.join(BASE, "logs", task + ".log")) if task + ".log" in logs else ""
    deliv.append("\nThe seat's report, from `logs/%s.log` (verbatim):\n" % task)
    deliv.append(fence(report) if report else "(no log)\n")

    # --- 5 Pass marks: quote what the commission set, verdict left to the moderator ---
    marks = re.findall(r"(?ims)^(#{2,} +(?:[0-9.]+ +)?pass marks?\b[^\n]*\n.*?)(?=^#+ |\Z)", commission)
    pm = ("The pass marks as commissioned (quoted from part 1):\n\n" + fence("".join(marks))
          if marks else "The commission names no pass-marks section; see part 1.\n")
    pm += "\n**%s.** The scribe does not judge pass marks.\n" % PENDING

    # --- 6 Scribe's note, through the local seat ---
    inside_records(os.path.join(RLOGS, "x"))
    os.makedirs(RLOGS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    np_ = os.path.join(RLOGS, "%s.note-%s.prompt.md" % (task, stamp))
    nr = os.path.join(RLOGS, "%s.note-%s.reply.md" % (task, stamp))
    nm = os.path.join(RLOGS, "%s.note-%s.meta.json" % (task, stamp))
    prompt = ("You are the Robot Factory's scribe. Write ONE plain paragraph (100 to 180 words) "
              "for the record of task %s. Say what was commissioned, what ran (attempts, exits, "
              "cost) and what was delivered. Use only facts in the material below. Do not judge "
              "whether pass marks are met, do not recommend anything, do not praise. No headings, "
              "no lists, no preamble.\n\n## Commission\n%s\n\n## What ran\n%s\n\n## Deliverables\n%s\n"
              % (task, commission, "\n".join(ran), "\n".join(deliv)))
    write(np_, prompt)
    for p in (nr, nm):
        inside_records(p)
    seat = os.path.join(BASE, "seats", "qwen_local.sh")
    rc = subprocess.run([seat, "--seat", "qwen-local", "--prompt", np_, "--out", nr, "--meta", nm],
                        stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True).returncode
    try:
        meta = json.loads(read(nm))
    except (OSError, ValueError):
        meta = {}
    reply = read(nr).strip() if os.path.isfile(nr) else ""
    if "<think>" in reply:
        reply = re.sub(r"(?s)<think>.*?</think>", "", reply).strip()
    para = re.sub(r"\s+", " ", reply).strip()          # one paragraph, as asked
    note_ok = rc == 0 and bool(para)
    append(os.path.join(RLOGS, "scribe-ledger.jsonl"), json.dumps({
        "t": now(), "round": task, "seat": "qwen-local", "phase": "actual", "purpose": "scribe-note",
        "in_tokens": meta.get("in_tokens"), "out_tokens": meta.get("out_tokens"),
        "cost_usd": meta.get("cost_usd"), "cost_source": meta.get("cost_source"),
        "model": meta.get("model"), "exit": meta.get("exit", "error"), "rc": rc,
        "cap_exceeded": meta.get("cap_exceeded"), "meta": rel(nm)}))
    if note_ok:
        note = (para + "\n\n*Drafted by the local seat `%s` (model `%s`, temperature %s, seed %s) "
                "through `seats/qwen_local.sh`; %s in / %s out tokens, $0.00 (local-free). "
                "Prompt, reply and meta: `%s`, `%s`, `%s`.*\n"
                % (meta.get("seat"), meta.get("model"), meta.get("temperature"), meta.get("seed"),
                   meta.get("in_tokens"), meta.get("out_tokens"), rel(np_), rel(nr), rel(nm)))
        if meta.get("exit") == "capped":
            note += "\n*The local seat hit its output cap; the note may be cut short.*\n"
    else:
        note = ("**Note not drafted.** The local seat returned rc %d (exit `%s`%s). Meta: `%s`.\n"
                % (rc, meta.get("exit", "unknown"),
                   ", %s" % meta["error"] if meta.get("error") else "", rel(nm)))

    # --- assemble ---
    rec = ["# Record: %s\n" % task,
           "*Assembled by bin/scribe.py on %s from done/, logs/, work/ and ledger.jsonl.*\n" % now(),
           "## 1. Commission\n", "From `done/%s.md`, verbatim:\n" % task, fence(commission, "markdown"),
           "## 2. What ran\n", "\n".join(ran) + "\n",
           "## 3. Deliverables\n", "\n".join(deliv),
           "## 4. Ledger\n",
           "The %d lines of `ledger.jsonl` with round `%s`, verbatim, in ledger order:\n" % (len(raw), task),
           fence("\n".join(s for s, _ in raw), "jsonl"),
           "## 5. Pass marks and moderator review\n", pm,
           "## 6. Scribe's note\n", note,
           "---\n", FOOTER + "\n"]
    write(out, "\n".join(rec))
    print("scribe: wrote %s (%d ledger lines, note %s)"
          % (rel(out), len(raw), "drafted" if note_ok else "NOT drafted"))
    return 0 if note_ok else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
