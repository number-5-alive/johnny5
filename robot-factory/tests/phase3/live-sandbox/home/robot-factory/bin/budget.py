#!/usr/bin/env python3
"""Robot Factory Phase 2 (task 006, 2026-10-31): estimate, pre-flight, ledger.

Draft for Dan's review. Stdlib only. Called by run-next.sh as
    python3 -I bin/budget.py preflight <base> <task.md> <name>
    python3 -I bin/budget.py actual    <base> <name> <meta_rel> <call_id> <worst_usd>

preflight: reads budget.yaml and the task file, verifies an approval if the
  task needs one, computes the worst case, checks the monthly ceiling, and
  appends exactly ONE ledger line:
    phase "planned"  -> prints  PLAN <call_id> <cli_budget_usd> <worst_usd> <max_out> <autocompact>  (exit 0)
    phase "refused"  -> prints  REFUSED <reason>  (exit 5); no model call may follow.
  A refusal writes no planned line, so no planned line is ever left dangling
  by a refusal. If budget.yaml or the ledger cannot be read, it refuses
  (fails closed); if even the refusal line cannot be written, exit 6.
actual: appends the "actual" line from the run's meta (Phase 1 shape plus
  call_id and worst_usd). Missing cost data writes nothing, exit 4.
"""
import datetime, hashlib, json, os, re, sys

# ---------- budget.yaml (minimal, fail-closed parser) ----------

def load_budget(path):
    out, section = {}, None
    with open(path) as f:
        for n, raw in enumerate(f, 1):
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            m = re.fullmatch(r"( {2})?([a-z_][a-z0-9_]*):(?: +(\S.*))?", line)
            if not m:
                raise ValueError("budget.yaml line %d not understood" % n)
            indent, key, val = m.groups()
            if indent is None:
                if val is None:
                    section = key; out[key] = {}
                    continue
                section = None
                out[key] = conv(val)
            else:
                if section is None or val is None:
                    raise ValueError("budget.yaml line %d: bad nesting" % n)
                out[section][key] = conv(val)
    return out

def conv(v):
    v = v.strip()
    if v in ("on", "true", "yes"): return True
    if v in ("off", "false", "no"): return False
    if re.fullmatch(r"-?\d+", v): return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v): return float(v)
    return v

def need_num(b, dotted):
    cur = b
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            raise ValueError("budget.yaml missing %s" % dotted)
        cur = cur[k]
    if isinstance(cur, bool) or not isinstance(cur, (int, float)) or cur < 0:
        raise ValueError("budget.yaml %s is not a non-negative number" % dotted)
    return cur

def need_str(b, dotted):
    cur = b
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            raise ValueError("budget.yaml missing %s" % dotted)
        cur = cur[k]
    return str(cur)

# ---------- ledger ----------

def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

def append_line(base, obj):
    with open(os.path.join(base, "ledger.jsonl"), "a") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")

def month_to_date(base, month):
    """Actual spend this month + worst case of planned lines with no actual.

    Spec 3.4: a planned line with no matching actual is counted at its worst
    case until reconciled by hand. Planned and actual pair on call_id.
    Lines are bucketed by the month in their own "t" (local time).
    """
    actual, planned, closed = 0.0, {}, set()
    path = os.path.join(base, "ledger.jsonl")
    if not os.path.exists(path):
        return 0.0, 0.0, 0
    with open(path) as f:
        for n, raw in enumerate(f, 1):
            if not raw.strip():
                continue
            j = json.loads(raw)            # a corrupt ledger raises: fail closed
            if str(j.get("t", ""))[:7] != month:
                continue
            ph = j.get("phase")
            if ph == "actual":
                actual += float(j.get("cost_usd") or 0)
                if j.get("call_id"): closed.add(j["call_id"])
            elif ph == "planned" and j.get("call_id"):
                planned[j["call_id"]] = float(j.get("worst_usd") or 0)
            elif ph == "reconciled" and j.get("call_id"):
                closed.add(j["call_id"])   # Dan's hand reconciliation (future)
    open_ = {k: v for k, v in planned.items() if k not in closed}
    return actual, sum(open_.values()), len(open_)

# ---------- task file ----------

CAP_RE = re.compile(r"CAP_USD: ([0-9]+(?:\.[0-9]{1,2})?)")

def task_terms(text):
    """Header lines a task may carry. Malformed or repeated ones are refused."""
    caps = [l for l in text.splitlines() if l.startswith("CAP_USD:")]
    appr = [l for l in text.splitlines() if l.startswith("APPROVAL:")]
    if len(caps) > 1: raise ValueError("more than one CAP_USD line")
    if len(appr) > 1: raise ValueError("more than one APPROVAL line")
    cap = None
    if caps:
        m = CAP_RE.fullmatch(caps[0])
        if not m: raise ValueError("CAP_USD line malformed: %r" % caps[0][:60])
        cap = float(m.group(1))
    approval_req = False
    if appr:
        if appr[0] != "APPROVAL: required":
            raise ValueError("APPROVAL line malformed: %r" % appr[0][:60])
        approval_req = True
    return cap, approval_req

# Phase 3 (task 009): seat selection. The only accepted form is the exact
# line "SEAT: qwen_local" (set by Alex on Dan's commission, like SCOPE:).
# No SEAT line = the Claude seat, exactly as before. Any other line that
# starts with "SEAT:" is refused, never guessed at.
SEATS = {"qwen_local": "qwen-local"}

def task_seat(text):
    lines = [l for l in text.splitlines() if l.startswith("SEAT:")]
    if not lines:
        return "claude-code"
    if len(lines) > 1: raise ValueError("more than one SEAT line")
    m = re.fullmatch(r"SEAT: ([a-z_]+)", lines[0])
    if not m or m.group(1) not in SEATS:
        raise ValueError("SEAT line not recognised: %r" % lines[0][:60])
    return SEATS[m.group(1)]

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)
    return h.hexdigest()

def check_approval(base, task, name):
    """Approval exists; hash matches the file NOW; approval newer than its last change.

    The operative approval is the LAST line of approvals/<name>.jsonl
    (written only by approve.sh, append-only). Returns (ok, why, record_ref).
    """
    path = os.path.join(base, "approvals", name + ".jsonl")
    ref = "approvals/%s.jsonl" % name
    if not os.path.exists(path):
        return False, "approval required but none found (%s)" % ref, None
    lines = [l for l in open(path).read().splitlines() if l.strip()]
    if not lines:
        return False, "approval file empty (%s)" % ref, None
    try:
        rec = json.loads(lines[-1])
    except Exception:
        return False, "last approval record unreadable (%s)" % ref, None
    ref = "%s#%d" % (ref, len(lines))
    now_hash = sha256(task)
    if rec.get("sha256") != now_hash:
        return False, "hash mismatch: approved %s, file now %s (%s)" % (
            str(rec.get("sha256"))[:12], now_hash[:12], ref), ref
    mtime = os.stat(task).st_mtime
    ep = rec.get("epoch")
    if not isinstance(ep, (int, float)) or ep <= mtime:
        return False, "approval (%s) not newer than the file's last change (%s) (%s)" % (
            rec.get("t"), datetime.datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="seconds"), ref), ref
    return True, "approved %s, hash %s" % (rec.get("t"), now_hash[:12]), ref

# ---------- preflight ----------

def preflight(base, task, name):
    t0 = now_iso()
    seat = "claude-code"
    call_id = "%s@%s" % (name, t0)

    def refuse(reason, **extra):
        line = {"t": t0, "round": name, "seat": seat, "phase": "refused",
                "reason": reason}
        line.update(extra)
        try:
            append_line(base, line)
        except Exception as e:
            print("REFUSED %s (and the ledger refusal line could NOT be written: %s)" % (reason, e))
            sys.exit(6)
        print("REFUSED " + reason)
        sys.exit(5)

    # Phase 3: the seat is read first, so every line (planned or refused)
    # names the seat the task asked for. Unreadable task: refused as claude-code.
    try:
        text = open(task, encoding="utf-8").read()
        seat = task_seat(text)
        req_cap, approval_flag = task_terms(text)
    except Exception as e:
        refuse("task file not acceptable: %s" % e)
    local = seat == "qwen-local"

    try:
        b = load_budget(os.path.join(base, "budget.yaml"))
        ceiling = need_num(b, "monthly_ceiling_usd")
        default_cap = need_num(b, need_str(b, "queue.default_cap_from"))
        cls = "local" if local else need_str(b, "queue.seat_class")
        max_in = need_num(b, cls + ".max_in_tokens")
        max_out = need_num(b, cls + ".max_out_tokens")
        reserve = need_num(b, "queue.overshoot_reserve_usd")
        autocompact = need_num(b, "queue.autocompact_tokens")
        cpt = need_num(b, "queue.chars_per_token")
        if cpt <= 0: raise ValueError("queue.chars_per_token must be > 0")
    except Exception as e:
        refuse("budget.yaml unusable: %s" % e)

    # 1. Effective cap. A task may LOWER its cap on its own text; raising it
    #    needs Dan's approval. APPROVAL: required asks for approval regardless.
    cap = default_cap if req_cap is None else req_cap
    reasons = []
    if req_cap is not None and req_cap > default_cap:
        reasons.append("cap override $%.2f > default $%.2f" % (req_cap, default_cap))
    if approval_flag:
        reasons.append("task says APPROVAL: required")
    approval_ref = None
    if reasons:
        ok, why, approval_ref = check_approval(base, task, name)
        if not ok:
            refuse("not approved: " + why, needs_approval_for="; ".join(reasons),
                   cap_usd=cap)

    # 2. Prompt size against the per-call input cap (spec 5.2: chars / 3).
    est_in = int(-(-len(text) // cpt))
    if est_in > max_in:
        refuse("prompt estimate %d tokens > max_in_tokens %d" % (est_in, max_in),
               est_prompt_tokens=est_in, cap_usd=cap)

    # 3. Worst case. The CLI stops after the request that crosses its budget,
    #    so it gets (cap - reserve) and the crossing request has `reserve` of
    #    headroom: worst case = cap.
    #    Phase 3: a local seat is free. Worst case $0, no CLI budget, no
    #    reserve; the token caps above and the approval rules still apply.
    if local:
        cli_budget, worst, reserve = 0.0, 0.0, 0.0
    else:
        cli_budget = round(cap - reserve, 2)
        if cli_budget <= 0:
            refuse("cap $%.2f does not exceed overshoot reserve $%.2f; worst case cannot be held to the cap" % (cap, reserve),
                   cap_usd=cap)
        worst = round(cap, 2)

    # 4. Monthly ceiling: month-to-date actual + open planned worst cases + this worst case.
    month = t0[:7]
    try:
        spent_actual, open_worst, n_open = month_to_date(base, month)
    except Exception as e:
        refuse("ledger unreadable for the ceiling check: %s" % e, cap_usd=cap)
    spent_before = round(spent_actual + open_worst, 6)
    # A $0 worst case adds nothing to the month, so a free seat is never
    # refused on dollars (an unreadable ledger above still refuses).
    if not local and spent_before + worst > ceiling:
        refuse("monthly ceiling: month-to-date $%.2f + worst case $%.2f = $%.2f > ceiling $%.2f" % (
                   spent_before, worst, spent_before + worst, ceiling),
               worst_usd=worst, spent_before_usd=spent_before, ceiling_usd=ceiling,
               month=month, cap_usd=cap)

    line = {"t": t0, "round": name, "seat": seat, "phase": "planned",
            "worst_usd": worst, "spent_before_usd": spent_before,
            "call_id": call_id, "cap_usd": cap, "cli_budget_usd": cli_budget,
            "reserve_usd": reserve, "ceiling_usd": ceiling, "month": month,
            "open_planned": n_open, "est_prompt_tokens": est_in,
            "max_out_tokens": max_out, "approval": approval_ref}
    if local:
        line.update(seat_class="local", max_in_tokens=max_in, cli_budget_usd=None, reserve_usd=None)
    try:
        append_line(base, line)
    except Exception as e:
        print("REFUSED planned line could not be written: %s" % e); sys.exit(6)
    # Phase 3: the seat is a 7th field, appended so the first six keep their places.
    print("PLAN %s %.2f %.2f %d %d %s" % (call_id, cli_budget, worst, max_out, autocompact, seat))

# ---------- actual ----------

def actual(base, name, meta_rel, call_id, worst):
    try:
        with open(os.path.join(base, meta_rel)) as f: m = json.load(f)
    except Exception as e:
        print("ledger: NOT written (no readable meta: %s)" % type(e).__name__); sys.exit(4)
    need = ("model", "finished", "in_tokens", "out_tokens", "cost_usd")
    missing = [k for k in need if m.get(k) is None]
    if missing:
        print("ledger: NOT written (missing %s)" % ",".join(missing)); sys.exit(4)
    line = {"t": m["finished"], "round": name, "seat": m.get("seat"), "phase": "actual",
            "in_tokens": m["in_tokens"], "out_tokens": m["out_tokens"], "cost_usd": m["cost_usd"],
            "cost_source": m.get("cost_source"), "model": m["model"], "exit": m.get("exit"),
            "meta": meta_rel, "call_id": call_id, "worst_usd": float(worst)}
    # Phase 3: a seat that reports an input-cap overage carries it onto the
    # ledger line (the local seat always reports true/false). Claude lines
    # have no such key in their meta, so their shape is unchanged.
    if "cap_exceeded" in m:
        if not isinstance(m["cap_exceeded"], bool):
            print("ledger: NOT written (cap_exceeded not true/false)"); sys.exit(4)
        line["cap_exceeded"] = m["cap_exceeded"]
    append_line(base, line)
    msg = "ledger: appended (%s, $%s %s, worst case $%.2f)" % (meta_rel, m["cost_usd"], m.get("cost_source"), float(worst))
    if line.get("cap_exceeded"):
        msg += " WARNING: cap_exceeded (%s)" % m.get("cap_exceeded_detail", "input over local.max_in_tokens")
    if float(m["cost_usd"]) > float(worst):
        msg += " WARNING: actual EXCEEDS planned worst case; the overshoot reserve is too small"
    print(msg)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["preflight"] and len(a) == 4:
        preflight(*a[1:])
    elif a[:1] == ["actual"] and len(a) == 6:
        actual(*a[1:])
    else:
        print(__doc__); sys.exit(2)
