#!/usr/bin/env python3
"""Robot Factory scribe v1 (Phase 3, task 009, 2026-10-31). Draft for Dan's review.

    python3 bin/scribe.py <task> [--force]
    python3 bin/scribe.py --session <session-id> [--force]

Session mode (Phase 4, task 011, 2026-10-31): the commission is
sessions/<id>/brief.md, the session must be closed (session.json with a
status), deliverables are every file under sessions/<id>/ (round files,
call files, session.json, session.log), the report is session.log and the
logs are sessions/<id>/calls/*.log. Part 2 gains a rounds summary from
session.json. Parts, note, footer and the write gate are unchanged.

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

Phase 7 (task 015, 2026-11-01), SAINT:
    python3 bin/scribe.py --standings <session-id> <round>
  The standings turn. Reads sessions/<id>/r<round>-state.json (written by
  session.py before the round) and writes records/<id>-r<round>-standings.md
  (exclusive): per-seat positions, points answered vs open, disagreements
  outstanding, all computed from the record; then a short reading drafted by
  the local seat (labelled, no vote). Its own scribe-ledger line, purpose
  "standings". Same code at any seat count. Exit 0, or 3 if the reading was
  not drafted (the computed standings are still written).
  In --session mode, when session.json says decision_record, the scribe also
  writes records/<id>-decision-record.md: header (agenda, commission, seats and
  capacities), per-round positions verbatim, agreements and disagreements
  apart, dissent preserved, the chair's synthesis, and the closing stamp
  "SAINT decision record: agreement, not verification."

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
SAINT_STAMP = "SAINT decision record: agreement, not verification."
SAINT_HEADER = ("This record states agreement reached in a SAINT session, not verification. "
                "Consensus here is agreement only: nothing in it was run, tested or checked, and it "
                "carries no verified stamp and no Grasshopper stamp.")
STANDINGS_LABEL = ("Standings: record, not opinion. Computed by the scribe from the session record "
                   "before this round; it carries no vote.")


def local_seat(stem, prompt, purpose, rnd):
    """One call to the local seat through seats/qwen_local.sh; files and a
    scribe-ledger line under records/logs/. Returns (ok, text, meta, paths)."""
    inside_records(os.path.join(RLOGS, "x"))
    os.makedirs(RLOGS, exist_ok=True)
    np_, nr, nm = (os.path.join(RLOGS, stem + ext) for ext in (".prompt.md", ".reply.md", ".meta.json"))
    write(np_, prompt)
    for p in (nr, nm):
        inside_records(p)
    rc = subprocess.run([os.path.join(BASE, "seats", "qwen_local.sh"), "--seat", "qwen-local", "--prompt", np_,
                         "--out", nr, "--meta", nm], stdin=subprocess.DEVNULL, stderr=subprocess.PIPE,
                        text=True).returncode
    try:
        meta = json.loads(read(nm))
    except (OSError, ValueError):
        meta = {}
    reply = read(nr).strip() if os.path.isfile(nr) else ""
    reply = re.sub(r"(?s)<think>.*?</think>", "", reply).strip()
    para = re.sub(r"\s+", " ", reply).strip()
    append(os.path.join(RLOGS, "scribe-ledger.jsonl"), json.dumps({
        "t": now(), "round": rnd, "seat": "qwen-local", "phase": "actual", "purpose": purpose,
        "in_tokens": meta.get("in_tokens"), "out_tokens": meta.get("out_tokens"),
        "cost_usd": meta.get("cost_usd"), "cost_source": meta.get("cost_source"),
        "model": meta.get("model"), "exit": meta.get("exit", "error"), "rc": rc,
        "cap_exceeded": meta.get("cap_exceeded"), "meta": rel(nm)}))
    return rc == 0 and bool(para), para, meta, rc, (np_, nr, nm)


def cell(t):
    return str(t).replace("|", "\\|").replace("\n", " ")


def capacity_label(c):
    if c["capacity"] == "scribe":
        who = "Johnny (%s)" % c["seat"] if c.get("name") == "johnny" else c["seat"]
        return "scribe: %s, %s" % (who, c.get("path", "bin/scribe.py"))
    return c["capacity"]


def standings(sid, rnd):
    """The standings turn: state of the room from the record, no vote."""
    sdir = os.path.join(BASE, "sessions", sid)
    try:
        st = json.loads(read(os.path.join(sdir, "r%d-state.json" % rnd)))
    except (OSError, ValueError):
        die(2, "no readable sessions/%s/r%d-state.json" % (sid, rnd))
    out = os.path.join(RECORDS, "%s-r%d-standings.md" % (sid, rnd))
    if os.path.exists(out):
        die(2, "%s exists; standings are written once" % rel(out))
    steps = st.get("steps") or {}
    rounds = st.get("rounds") or []
    caps = st.get("capacities") or []
    L = ["# Standings before round %d: %s" % (rnd, sid), "", "*" + STANDINGS_LABEL + "*", "",
         "Agenda: %s" % st.get("agenda"), "",
         "## Positions per seat", ""]
    seats = []
    for c in caps:
        if c["votes"] and c["seat"] not in seats:
            seats.append(c["seat"])
    for seat in seats:
        roles = [c["capacity"] for c in caps if c["seat"] == seat and c["votes"]]
        others = [capacity_label(c) for c in caps if c["seat"] == seat and not c["votes"]]
        L.append("### %s (%s)" % (seat, ", ".join(roles) + ("; also " + "; ".join(others) + ", no vote" if others else "")))
        L.append("")
        for role in roles:
            step = steps.get(role)
            if step == "compose":
                v = (st.get("versions") or [None])[0]
                L.append("- As %s: opened with `%s`." % (role, v))
                if v and os.path.isfile(os.path.join(sdir, v)):
                    L += ["", fence(read(os.path.join(sdir, v)).strip(), "markdown")]
            elif step == "critique":
                for r in rounds:
                    raised = [p for p in r.get("raised") or [] if p["id"].startswith("P")]
                    L.append("- As %s, round %s: %s" % (role, r.get("round"), "raised %s." % ", ".join(
                        p["id"] for p in raised) if raised else "raised no substantive points."))
                    L += ["  - %s: %s" % (p["id"], p["point"]) for p in raised]
            elif step == "merge":
                for r in rounds:
                    dec = [p for p in r.get("raised") or [] if p.get("decision")]
                    if dec:
                        L.append("- As %s, round %s: accepted %s; rejected %s; restated as `%s`." % (
                            role, r.get("round"), ", ".join(p["id"] for p in dec if p["decision"] == "ACCEPT") or "none",
                            ", ".join(p["id"] for p in dec if p["decision"] == "REJECT") or "none", r.get("produced")))
                    else:
                        L.append("- As %s, round %s: no decisions recorded." % (role, r.get("round")))
        L.append("")
    allp = [(r.get("round"), p) for r in rounds for p in r.get("raised") or []]
    acc = [x for x in allp if x[1].get("decision") == "ACCEPT"]
    rej = [x for x in allp if x[1].get("decision") == "REJECT"]
    opn = [x for x in allp if not x[1].get("decision")]
    L += ["## Points answered vs open", "",
          "Raised %d; answered %d (accepted %d, rejected %d); open %d." % (len(allp), len(acc) + len(rej), len(acc), len(rej), len(opn)),
          ""]
    if allp:
        L += ["| Round | Point | Raised | Status | Chair's reason |", "|---|---|---|---|---|"]
        L += ["| %s | %s | %s | %s | %s |" % (r, p["id"], cell(p["point"]),
                                            {"ACCEPT": "answered: accepted", "REJECT": "answered: rejected"}.get(p.get("decision"), "open"),
                                            cell(p.get("reason") or "")) for r, p in allp]
    else:
        L.append("No points raised yet.")
    L += ["", "## Disagreements outstanding", ""]
    L += ["- Round %s %s: %s  \n  Chair rejected: %s" % (r, p["id"], p["point"], p["reason"]) for r, p in rej] or [
        "None: no point has been rejected."]
    L += ["", "(M points are the session's mechanical checks, not a seat's objection.)" if any(
        p["id"].startswith("M") for _, p in allp) else ""]
    computed = "\n".join(L).rstrip() + "\n"
    ok, para, meta, rc, paths = local_seat(
        "%s.standings-r%d" % (sid, rnd),
        "You are the scribe of a SAINT deliberation. You hold no vote. In two or three plain sentences, "
        "restate the tally below: how many points were raised, answered and open, and which disagreements "
        "remain. Do not take a side, do not judge who is right, do not recommend anything.\n\n" + computed,
        "standings", sid)
    if ok:
        reading = ("## Scribe's reading (restates the tally; no vote)\n\n" + para +
                   "\n\n*Drafted by the local seat `%s` (model `%s`) through `seats/qwen_local.sh`; %s, $%s.*\n"
                   % (meta.get("seat"), meta.get("model"), meta.get("cost_source"), meta.get("cost_usd")))
    else:
        reading = ("## Scribe's reading\n\n**Reading not drafted.** The local seat returned rc %d (exit `%s`). "
                   "The computed standings above stand on their own.\n" % (rc, meta.get("exit", "unknown")))
    inside_records(out)
    with open(out, "x", encoding="utf-8") as f:
        f.write(computed + "\n" + reading + "\n---\n" + FOOTER + "\n")
    print("scribe: wrote %s (reading %s)" % (rel(out), "drafted" if ok else "NOT drafted"))
    return 0 if ok else 3


def decision_record(task, sess, sdir, commission):
    """records/<sid>-decision-record.md. Agreement, not verification."""
    def call_text(stem, kind):
        p = os.path.join(sdir, "calls", "%s.%s.md" % (stem, kind)) if stem else ""
        return read(p).strip() if p and os.path.isfile(p) else None
    caps = sess.get("capacities") or []
    steps = sess.get("steps") or {}
    role_of = {v: k for k, v in steps.items()}
    seat_of = sess.get("seats") or {}
    rounds = sess.get("rounds") or []
    L = ["# SAINT decision record: %s" % task, "",
         "> " + SAINT_HEADER, "",
         "*Assembled by bin/scribe.py on %s from `sessions/%s/`. The scribe holds no vote.*" % (now(), task), "",
         "## Header", "",
         "- Agenda: %s (%s)" % (sess.get("agenda"), sess.get("agenda_source")),
         "- Ruleset: `%s` (budget section `%s`, word-only: %s)" % (sess.get("ruleset"), sess.get("budget_section"),
                                                                   "yes" if sess.get("word_only") else "no"),
         "- Status: **%s**: %s. Rounds allowed %s, rounds held %d." % (sess.get("status"), sess.get("stop_reason"),
                                                                     sess.get("rounds_allowed"), len(rounds)),
         "", "### Seats and capacities", "",
         "| Seat | Capacity | Vote |", "|---|---|---|"]
    L += ["| `%s` | %s | %s |" % (c["seat"], cell(capacity_label(c)), "votes" if c["votes"] else "no vote") for c in caps]
    L += ["", "### Commission", "", "From `sessions/%s/brief.md`, verbatim:" % task, "", fence(commission, "markdown")]
    L += ["## Positions by round (verbatim)", ""]
    op = role_of.get("compose")
    opening = call_text("01-%s-compose" % op, "reply") if op else None
    L += ["### Round 0: opening", "", "#### %s (`%s`)" % (op, seat_of.get(op)), "",
          fence(opening, "markdown") if opening is not None else "(no reply on file)\n"]
    cr, mr = role_of.get("critique"), role_of.get("merge")
    for r in rounds:
        L += ["### Round %s" % r.get("round"), ""]
        if r.get("standings"):
            L += ["Standings in front of the seats: `sessions/%s/%s` (record, not opinion; no vote)." % (task, r["standings"]), ""]
        t = call_text(r.get("critique_call"), "reply")
        L += ["#### %s (`%s`)" % (cr, seat_of.get(cr)), "", fence(t, "markdown") if t is not None else "(no reply on file)\n"]
        t = call_text(r.get("merge_call"), "reply")
        if r.get("merge_call"):
            L += ["#### %s (`%s`)" % (mr, seat_of.get(mr)), "", fence(t, "markdown") if t is not None else "(no reply on file)\n"]
        else:
            L += ["#### %s (`%s`)" % (mr, seat_of.get(mr)), "", "No merge this round (%s)." % (
                "the challenger raised no points" if not r.get("raised") else "the session stopped first"), ""]
    allp = [(r.get("round"), p) for r in rounds for p in r.get("raised") or []]
    L += ["## Agreements (accepted by the chair)", ""]
    L += ["- Round %s %s: %s  \n  Accepted: %s" % (r, p["id"], p["point"], p["reason"])
          for r, p in allp if p.get("decision") == "ACCEPT"] or ["None."]
    L += ["", "## Disagreements (rejected by the chair)", ""]
    rej = [(r, p) for r, p in allp if p.get("decision") == "REJECT"]
    L += ["- Round %s %s: %s  \n  Rejected: %s" % (r, p["id"], p["point"], p["reason"]) for r, p in rej] or ["None."]
    opn = [(r, p) for r, p in allp if not p.get("decision")]
    if opn:
        L += ["", "Unanswered when the session stopped:"] + ["- Round %s %s: %s" % (r, p["id"], p["point"]) for r, p in opn]
    L += ["", "## Dissent (preserved)", "",
          "Objections the chair rejected, in the %s's own words. They stand in the record beside the synthesis; "
          "agreement in the room does not erase them." % cr, ""]
    dis = [(r, p) for r, p in rej + opn if p["id"].startswith("P")]
    L += ["> Round %s %s (%s, `%s`): %s" % (r, p["id"], cr, seat_of.get(cr), p["point"]) for r, p in dis] or [
        "No dissent on record: the chair rejected no objection."]
    L += ["", "## Chair's synthesis", ""]
    fv = sess.get("final_version")
    if rounds and any(r.get("record") for r in rounds) and fv:
        L += ["The chair's last restated position, `%s`, verbatim. It is agreement reached in this room, "
              "not verification." % fv, "", fence(read(os.path.join(sdir, fv)).strip(), "markdown")]
    else:
        L += ["The chair made no synthesis: no merge took place. The standing position is the opening, `%s`." % fv, ""]
    st = [r["standings"] for r in rounds if r.get("standings")]
    L += ["## Standings turns", ""]
    L += ["- `sessions/%s/%s` (copy of `records/%s`)" % (task, s, "%s-%s" % (task, s)) for s in st] or [
        "None (the session held one round or fewer)."]
    L += ["", "---", "", FOOTER, "", SAINT_STAMP]
    return "\n".join(L) + "\n"


def main(argv):
    if argv[:1] == ["--standings"]:
        if len(argv) != 3 or not re.fullmatch(r"[0-9]{3}[-a-z0-9]*", argv[1]) or not re.fullmatch(r"[1-9][0-9]*", argv[2]):
            die(2, "usage: scribe.py --standings <session-id> <round>")
        return standings(argv[1], int(argv[2]))
    return record(argv)


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


def record(argv):
    args = [a for a in argv if a not in ("--force", "--session")]
    force = "--force" in argv
    smode = "--session" in argv
    if len(args) != 1 or not re.fullmatch(r"[0-9]{3}[-a-z0-9]*", args[0]):
        die(2, "usage: scribe.py [--session] <task> [--force]   (task like 008-maps-gate-pack)")
    task = args[0]
    prefix = task.split("-")[0]
    sess = None
    if smode:
        sdir = os.path.join(BASE, "sessions", task)
        done = os.path.join(sdir, "brief.md")
        try:
            sess = json.loads(read(os.path.join(sdir, "session.json")))
        except (OSError, ValueError):
            die(2, "no readable sessions/%s/session.json: the scribe records closed sessions only" % task)
        if not sess.get("status"):
            die(2, "session %s has no status: not closed" % task)
    else:
        done = os.path.join(BASE, "done", task + ".md")
    if not os.path.isfile(done):
        die(2, "no %s: the scribe records finished tasks only" % rel(done))
    out = os.path.join(RECORDS, task + "-record.md")
    if os.path.exists(out) and not force:
        die(2, "%s exists; the scribe does not overwrite a record without --force" % rel(out))
    dout = os.path.join(RECORDS, task + "-decision-record.md") if sess and sess.get("decision_record") else None
    if dout and os.path.exists(dout) and not force:
        die(2, "%s exists; the scribe does not overwrite a record without --force" % rel(dout))

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
    if smode:
        logs = sorted(rel(os.path.join(sdir, "calls", f)) for f in os.listdir(os.path.join(sdir, "calls"))
                      if f.endswith(".log")) if os.path.isdir(os.path.join(sdir, "calls")) else []
        ran.append("Logs: " + (", ".join("`%s`" % f for f in logs) or "none found") + ".")
        ran.append("\n### Rounds (from `sessions/%s/session.json`)\n" % task)
        ran.append("- Ruleset `%s`, seats %s. Status **%s**: %s. Rounds allowed %s; final version `%s`; final checks %s."
                   % (sess.get("ruleset"), json.dumps(sess.get("seats"), sort_keys=True), sess.get("status"),
                      sess.get("stop_reason"), sess.get("rounds_allowed"), sess.get("final_version"),
                      json.dumps(sess.get("final_checks"), sort_keys=True)))
        ran.append("- Versions, in order: " + (", ".join("`%s`" % v for v in sess.get("versions") or []) or "none") + ".")
        for r in sess.get("rounds") or []:
            ran.append("- Round %s: critique of `%s` raised %s critic and %s mechanical point(s)%s."
                       % (r.get("round"), r.get("critiqued"), r.get("points"), r.get("mech_points"),
                          "; merge accepted %s, rejected %s, produced `%s`" % (
                              ", ".join(r.get("accepted") or []) or "none",
                              ", ".join(r.get("rejected") or []) or "none", r.get("produced"))
                          if r.get("record") else "; no merge"))
            for d in r.get("disagreements") or []:
                ran.append("  - Disagreement %s: %s Rejected because: %s" % (d.get("id"), d.get("point"), d.get("reason")))
    else:
        logs = sorted(f for f in os.listdir(os.path.join(BASE, "logs"))
                      if f.endswith(".log") and (f == task + ".log" or f.startswith(task + ".")))
        ran.append("Logs: " + (", ".join("`logs/%s`" % f for f in logs) or "none found") + ".")

    # --- 3 Deliverables ---
    if smode:
        files = sorted(rel(os.path.join(d, f)) for d, _, fs in os.walk(sdir) for f in fs)
        rpath = os.path.join(sdir, "session.log")
    else:
        files = sorted("work/" + f for f in os.listdir(os.path.join(BASE, "work"))
                       if f.startswith(prefix + "-") and os.path.isfile(os.path.join(BASE, "work", f)))
        rpath = os.path.join(BASE, "logs", task + ".log")
    deliv = ["| File | Bytes | sha256 |", "|---|---|---|"]
    for f in files:
        b = open(os.path.join(BASE, f), "rb").read()
        deliv.append("| `%s` | %d | `%s` |" % (f, len(b), hashlib.sha256(b).hexdigest()))
    if not files:
        deliv = ["No files matching `work/%s-*`." % prefix]
    report = read(rpath) if os.path.isfile(rpath) and (smode or task + ".log" in logs) else ""
    deliv.append("\nThe %s, from `%s` (verbatim):\n" % ("session log" if smode else "seat's report", rel(rpath)))
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
           "*Assembled by bin/scribe.py on %s from %s and ledger.jsonl.*\n"
           % (now(), "sessions/%s/" % task if smode else "done/, logs/, work/"),
           "## 1. Commission\n", "From `%s`, verbatim:\n" % rel(done), fence(commission, "markdown"),
           "## 2. What ran\n", "\n".join(ran) + "\n",
           "## 3. Deliverables\n", "\n".join(deliv),
           "## 4. Ledger\n",
           "The %d lines of `ledger.jsonl` with round `%s`, verbatim, in ledger order:\n" % (len(raw), task),
           fence("\n".join(s for s, _ in raw), "jsonl"),
           "## 5. Pass marks and moderator review\n", pm,
           "## 6. Scribe's note\n", note,
           "---\n", FOOTER + "\n"]
    write(out, "\n".join(rec))
    if dout:
        write(dout, decision_record(task, sess, sdir, commission))
        print("scribe: wrote %s" % rel(dout))
    print("scribe: wrote %s (%d ledger lines, note %s)"
          % (rel(out), len(raw), "drafted" if note_ok else "NOT drafted"))
    return 0 if note_ok else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
