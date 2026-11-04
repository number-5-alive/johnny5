#!/usr/bin/env python3
"""Robot Factory Phase 2 (task 006, 2026-10-31): estimate, pre-flight, ledger.

Draft for Dan's review. Stdlib only. Called by run-next.sh as
    python3 -I bin/budget.py preflight <base> <task.md> <name> [<call time, date -Is>]
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
    python3 -I bin/budget.py summary   <base> [YYYY-MM]

Phase 5 (task 012, 2026-11-01): billing classes. Seats come from
seats/registry.json (billing subscription|api|local, meter usd|tokens).
Planned and actual lines now carry "billing" and "meter"; lines from before
012 carry neither and read as local (qwen-local) or subscription/usd
(everything else), so every old line stays valid. A token-metered seat
(codex, gemini-cli: the CLI states no dollar figure) writes cost_usd null,
cost_source "not-reported-tokens-only", worst_usd null + worst_tokens, and is
paced in tokens per seat. Only subscription seats may be token-metered; an
api seat must report dollars or nothing is written (exit 4). The api class
has its own ceiling (api_monthly_ceiling_usd). Tallies are never summed.

Phase 6 (task 014, 2026-11-01): api seats (registry "api" block, token_class
api). Pre-flight for an api seat checks, in order: the key file (exists in
secrets/, regular, not a symlink, owned by the user, mode 600 or tighter,
readable; its CONTENT is never read here), then the prices (null = refused),
then worst case = max_in x price_in + max_out x price_out (+ per-call fee),
rounded up to the cent, against the task cap and api_monthly_ceiling_usd.
Status awaiting-key is not routable. An api actual must carry
price_source and a cost_usd that matches tokens x the registry prices.

Task 026b (2026-11-02): tiered scope approval (amendment of 2026-11-01).
A line "SCOPE: build-read" or "SCOPE: build-write" (a bare "SCOPE: build" is
build-write) declares widened reach; any other "SCOPE:" line, or more than
one, is refused. On the tool-bearing seat (claude-code) build-write needs
Dan's approval (approvals/, approve.sh); build-read needs Dan's OR the
moderator's (approvals-moderator/, bin/moderator_approve.py; same sha256 +
newer-than-mtime discipline, plus approver "moderator" and a commission).
On word-only seats SCOPE widens nothing and needs nothing, as before. The
PLAN line gains two fields: <scope> <approval> (approval = dan:<epoch>,
moderator:<epoch> or -). Cap overrides and APPROVAL: required stay Dan-only.
    python3 -I bin/budget.py grant <base> <home> <settings-out>
grant: writes the build-read permission settings for the claude seat and
  prints the read directories to add, one per line. approvals/,
  approvals-moderator/ and secrets/ are never in the grant (denied).

Task 033 (2026-11-02): projection meter. READ-ONLY; writes nothing, ever.
    python3 -I bin/budget.py project <planfile> [--json] [--base DIR]
project: plan (YAML or JSON: ruleset factory|saint, rounds, seats: [{seat,
  roles, calls}]) -> per seat expected (ledger history average x calls,
  session calls preferred; none = cap-bound = worst case) and worst case
  (per-call caps x calls). subscription in tokens, api in USD, local free;
  the classes are never added together. Malformed plan: refused, exit 3.
"""
import datetime, hashlib, json, math, os, re, stat, sys

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

def month_to_date(base, month, billing="subscription", seat=None, meter="usd"):
    """Actual spend this month + worst case of planned lines with no actual.

    Spec 3.4: a planned line with no matching actual is counted at its worst
    case until reconciled by hand. Planned and actual pair on call_id.
    Lines are bucketed by the month in their own "t" (local time).
    Phase 5: only lines of one billing class are counted (classes are never
    added together), optionally one ledger seat. meter "usd" sums cost_usd /
    worst_usd; meter "tokens" sums in+out tokens / worst_tokens.
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
            if ph == "reconciled" and j.get("call_id"):
                closed.add(j["call_id"])   # Dan's hand reconciliation (future)
                continue
            if line_class(j) != (billing, meter) or (seat and j.get("seat") != seat):
                if ph == "actual" and j.get("call_id"): closed.add(j["call_id"])
                continue
            if ph == "actual":
                if meter == "usd":
                    actual += float(j.get("cost_usd") or 0)
                else:
                    actual += float(j.get("in_tokens") or 0) + float(j.get("out_tokens") or 0)
                if j.get("call_id"): closed.add(j["call_id"])
            elif ph == "planned" and j.get("call_id"):
                planned[j["call_id"]] = float(j.get("worst_usd" if meter == "usd" else "worst_tokens") or 0)
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

# Task 026b: scope tiers. Exact lines only; anything else is refused.
SCOPES = {"SCOPE: build-read": "build-read", "SCOPE: build-write": "build-write",
          "SCOPE: build": "build-write"}       # legacy form: the safer reading wins

def task_scope(text):
    sc = [l for l in text.splitlines() if l.startswith("SCOPE:")]
    if len(sc) > 1: raise ValueError("more than one SCOPE line")
    if not sc: return "confined"
    if sc[0] not in SCOPES:
        raise ValueError("SCOPE line not recognised: %r (build-read, build-write, or legacy build)" % sc[0][:60])
    return SCOPES[sc[0]]

TOOL_SEATS = ("claude-code",)       # seats whose reach SCOPE actually widens

# Phase 3 (task 009): seat selection by the exact line "SEAT: <id>" (set by
# Alex on Dan's commission, like SCOPE:). No SEAT line = the Claude seat,
# exactly as before. Any other line that starts with "SEAT:" is refused,
# never guessed at.
# Phase 5 (task 012): the routable ids come from seats/registry.json: every
# registry seat with an adapter and status active or awaiting-login.
# Candidates (registry "candidates", e.g. jev) are never routable. If the
# registry file is ABSENT (a pre-012 tree), the Phase 3 table below applies
# unchanged; a registry that is present but malformed fails closed.
LEGACY_REGISTRY = {"seats": {
    "claude_code": {"ledger_seat": "claude-code", "adapter": "seats/claude_code.sh", "model": None,
                    "billing": "subscription", "meter": "usd", "token_class": "frontier", "status": "active"},
    "qwen_local": {"ledger_seat": "qwen-local", "adapter": "seats/qwen_local.sh", "model": "qwen3.6:27b",
                   "billing": "local", "meter": "usd", "token_class": "local", "status": "active"}},
    "candidates": {}}
BILLING = ("subscription", "api", "local")
METERS = ("usd", "tokens")
ROUTABLE = ("active", "awaiting-login")

def load_registry(base):
    path = os.path.join(base, "seats", "registry.json")
    if not os.path.exists(path):
        return LEGACY_REGISTRY
    with open(path) as f:
        r = json.load(f)
    seats = r.get("seats") if isinstance(r, dict) else None
    if not isinstance(seats, dict) or not seats:
        raise ValueError("seats/registry.json has no seats")
    ledger_ids = set()
    for sid, s in seats.items():
        if not re.fullmatch(r"[a-z_]+", sid) or not isinstance(s, dict):
            raise ValueError("registry seat %r malformed" % sid)
        for k in ("ledger_seat", "adapter", "token_class", "status"):
            if not isinstance(s.get(k), str) or not s[k]:
                raise ValueError("registry seat %s: %s missing" % (sid, k))
        if s.get("billing") not in BILLING or s.get("meter") not in METERS:
            raise ValueError("registry seat %s: billing/meter not recognised" % sid)
        if s["billing"] == "api" and s["meter"] != "usd":
            raise ValueError("registry seat %s: an api seat must be metered in usd" % sid)
        if s["ledger_seat"] in ledger_ids:
            raise ValueError("registry: ledger seat %s used twice" % s["ledger_seat"])
        ledger_ids.add(s["ledger_seat"])
    cands = r.get("candidates", {})
    if not isinstance(cands, dict) or set(cands) & set(seats):
        raise ValueError("registry candidates malformed or overlapping seats")
    return r

def seat_by_ledger(reg, ledger_seat):
    for sid, s in reg["seats"].items():
        if s["ledger_seat"] == ledger_seat:
            return sid, s
    return None, None

def task_seat(text, reg=None):
    reg = LEGACY_REGISTRY if reg is None else reg
    lines = [l for l in text.splitlines() if l.startswith("SEAT:")]
    if not lines:
        return "claude-code"
    if len(lines) > 1: raise ValueError("more than one SEAT line")
    m = re.fullmatch(r"SEAT: ([a-z_]+)", lines[0])
    s = reg["seats"].get(m.group(1)) if m else None
    if not s or not s.get("adapter") or s.get("status") not in ROUTABLE:
        why = " (a CANDIDATE, not a seat)" if m and m.group(1) in reg.get("candidates", {}) else ""
        if s and s.get("status") == "awaiting-key":
            why = (" (api seat awaiting-key: not routable until Dan creates its key file and sets"
                   " status active; prices CANDIDATE until Dan ratifies them)")
        raise ValueError("SEAT line not recognised%s: %r" % (why, lines[0][:60]))
    return s["ledger_seat"]

# ---------- api seats (Phase 6, task 014) ----------

def api_key_check(base, sreg):
    """(ok, why, path). Checks the key file's metadata only; never reads it."""
    api = sreg.get("api") if isinstance(sreg.get("api"), dict) else {}
    rel = api.get("key_file")
    if not isinstance(rel, str) or not re.fullmatch(r"secrets/[a-z_]+\.key", rel):
        return False, "no key_file of the form secrets/<id>.key in the registry api block", None
    path = os.path.join(base, rel)
    sdir = os.path.join(base, "secrets")
    try:
        d = os.lstat(sdir)
        if not stat.S_ISDIR(d.st_mode):
            return False, "secrets/ is not a directory", rel
        st = os.lstat(path)
    except FileNotFoundError:
        return False, "key file %s missing (Dan creates it: see secrets/README.md)" % rel, rel
    except OSError as e:
        return False, "key file %s not checkable: %s" % (rel, type(e).__name__), rel
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return False, "key file %s is not a regular file (symlinks refused)" % rel, rel
    if st.st_uid != os.geteuid():
        return False, "key file %s not owned by this user" % rel, rel
    if st.st_mode & 0o177:
        return False, "key file %s mode %03o is wider than 600 (chmod 600 %s)" % (
            rel, stat.S_IMODE(st.st_mode), rel), rel
    if not os.access(path, os.R_OK):
        return False, "key file %s unreadable" % rel, rel
    if st.st_size == 0:
        return False, "key file %s is empty" % rel, rel
    return True, "key file %s ok (mode %03o)" % (rel, stat.S_IMODE(st.st_mode)), rel

def _price(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0

def api_prices(sreg):
    """(ok, why, (p_in, p_out, p_call, source)). Null or missing = unpriced = refused."""
    api = sreg.get("api") if isinstance(sreg.get("api"), dict) else {}
    pin, pout = api.get("price_in_per_mtok_usd"), api.get("price_out_per_mtok_usd")
    pcall = api.get("price_per_call_usd", 0) if "price_per_call_usd" in api else 0
    src = api.get("price_source")
    bad = [k for k, v in (("price_in_per_mtok_usd", pin), ("price_out_per_mtok_usd", pout),
                          ("price_per_call_usd", pcall)) if not _price(v)]
    if bad:
        return False, "unpriced-api: %s null or not a price in the registry" % ",".join(bad), None
    if not isinstance(src, str) or not src.strip():
        return False, "unpriced-api: price_source missing in the registry", None
    return True, "priced (%s)" % src, (float(pin), float(pout), float(pcall), src)

def api_cost(prices, in_tokens, out_tokens):
    pin, pout, pcall, _ = prices
    return round(in_tokens * pin / 1e6 + out_tokens * pout / 1e6 + pcall, 8)

def line_class(j):
    """(billing, meter) of a ledger line. Lines from before task 012 carry
    neither key: qwen-local was local, everything else subscription USD."""
    billing = j.get("billing") or ("local" if j.get("seat") == "qwen-local" else "subscription")
    return billing, j.get("meter") or "usd"

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)
    return h.hexdigest()

def check_approval(base, task, name, who="dan"):
    """Approval exists; hash matches the file NOW; approval newer than its last change.

    The operative approval is the LAST line of approvals/<name>.jsonl
    (written only by approve.sh, append-only). Returns (ok, why, record_ref).
    026b: who="moderator" reads approvals-moderator/<name>.jsonl instead
    (bin/moderator_approve.py); the record must also say approver
    "moderator", name this task, and carry a commission. Only that one
    directory under the Factory root is read: a symlinked directory or file
    is refused, so a record planted anywhere else (e.g. work/) counts for nothing.
    """
    d = "approvals" if who == "dan" else "approvals-moderator"
    path = os.path.join(base, d, name + ".jsonl")
    ref = "%s/%s.jsonl" % (d, name)
    if who != "dan" and (os.path.islink(os.path.join(base, d)) or os.path.islink(path)):
        return False, "moderator approval path is a symlink, refused (%s)" % ref, None
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
    if not isinstance(rec, dict):
        return False, "last approval record unreadable (%s)" % ref, ref
    if who != "dan":
        if rec.get("approver") != "moderator" or rec.get("name") != name:
            return False, "last record is not a moderator approval for %s (%s)" % (name, ref), ref
        if not isinstance(rec.get("commission"), str) or not rec["commission"].strip():
            return False, "moderator record names no commission (%s)" % ref, ref
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

def preflight(base, task, name, t0=None):
    # 009b: the runner may pass its own call time (date -Is) so the call_id and
    # the per-call file names (logs/<name>@<stamp>.*) share one stamp.
    if t0 is None:
        t0 = now_iso()
    elif not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", t0):
        print("preflight: bad call time %r" % t0); sys.exit(2)
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
        reg = load_registry(base)
    except Exception as e:
        refuse("seats/registry.json unusable: %s" % e)
    try:
        text = open(task, encoding="utf-8").read()
        seat = task_seat(text, reg)
        req_cap, approval_flag = task_terms(text)
        scope = task_scope(text)
    except Exception as e:
        refuse("task file not acceptable: %s" % e)
    sid, sreg = seat_by_ledger(reg, seat)
    if sreg is None:
        refuse("seat %s not in the registry" % seat)
    billing, meter = sreg["billing"], sreg["meter"]
    local = billing == "local"
    # Phase 6: an api seat is checked key file -> prices -> (below) ceiling.
    prices = None
    if billing == "api":
        ok, why, _ = api_key_check(base, sreg)
        if not ok:
            refuse("api seat %s: %s" % (sid, why), billing="api", meter="usd")
        ok, why, prices = api_prices(sreg)
        if not ok:
            refuse("api seat %s: %s" % (sid, why), billing="api", meter="usd")
    tokens = meter == "tokens"         # Phase 5: no dollar figure, tallied in tokens

    try:
        b = load_budget(os.path.join(base, "budget.yaml"))
        ceiling = need_num(b, "monthly_ceiling_usd")
        if billing == "api":
            ceiling = need_num(b, "api_monthly_ceiling_usd")
        default_cap = need_num(b, need_str(b, "queue.default_cap_from"))
        if seat == "claude-code":
            cls = need_str(b, "queue.seat_class")
        else:
            cls = sreg["token_class"]
        pacing = need_num(b, cls + ".monthly_pacing_tokens") if tokens else None
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
    widened = scope != "confined" and seat in TOOL_SEATS
    if widened and scope == "build-write":
        reasons.append("SCOPE: build-write (or legacy SCOPE: build) is Dan-only")
    approval_ref, approver = None, None
    if reasons:
        ok, why, approval_ref = check_approval(base, task, name)
        if not ok:
            if widened and scope == "build-write":
                why += "; build-write is satisfied only by Dan's approval (approve.sh), never by a moderator approval"
                if check_approval(base, task, name, "moderator")[0]:
                    why += " (a valid moderator record exists and does not count)"
            refuse("not approved: " + why, needs_approval_for="; ".join(reasons),
                   cap_usd=cap, scope=scope)
        approver = "dan"
    elif widened:      # build-read: Dan's approval or the moderator's
        ok, why, approval_ref = check_approval(base, task, name)
        if ok:
            approver = "dan"
        else:
            okm, whym, refm = check_approval(base, task, name, "moderator")
            if not okm:
                refuse("not approved: SCOPE: build-read needs a moderator approval "
                       "(bin/moderator_approve.py -> approvals-moderator/) or Dan's approval "
                       "(approve.sh -> approvals/); moderator: %s; dan: %s" % (whym, why),
                       needs_approval_for="SCOPE: build-read", cap_usd=cap, scope=scope)
            approval_ref, approver = refm, "moderator"
    appr_tag = "-"
    if approver:
        rec = json.loads([l for l in open(os.path.join(base, approval_ref.split("#")[0])).read().splitlines() if l.strip()][-1])
        appr_tag = "%s:%.2f" % (approver, rec["epoch"])

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
    #    Phase 5: a token seat has no dollar worst case (the vendor states
    #    none, and none is estimated): worst_usd is null, worst_tokens is
    #    max_in + max_out, counted against the seat's monthly pacing figure.
    worst_tokens = None
    if local or tokens:
        cli_budget, worst, reserve = 0.0, 0.0, 0.0
        if tokens:
            worst_tokens = int(max_in + max_out)
    elif prices:
        # Phase 6: real dollars, priced from the registry, rounded UP to the cent.
        cli_budget, reserve = 0.0, 0.0
        worst = math.ceil(round(api_cost(prices, max_in, max_out) * 100, 6)) / 100
        if worst > cap:
            refuse("api worst case $%.2f (%d in x $%s + %d out x $%s per Mtok + $%s per call) > cap $%.2f" % (
                       worst, max_in, prices[0], max_out, prices[1], prices[2], cap),
                   worst_usd=worst, cap_usd=cap, billing="api", meter="usd")
    else:
        cli_budget = round(cap - reserve, 2)
        if cli_budget <= 0:
            refuse("cap $%.2f does not exceed overshoot reserve $%.2f; worst case cannot be held to the cap" % (cap, reserve),
                   cap_usd=cap)
        worst = round(cap, 2)

    # 4. Monthly ceiling: month-to-date actual + open planned worst cases + this worst case.
    #    Phase 5: counted within the seat's own billing class only. A token
    #    seat is checked in tokens against its pacing figure, per seat.
    month = t0[:7]
    try:
        if tokens:
            spent_actual, open_worst, n_open = month_to_date(base, month, billing, seat, "tokens")
        else:
            # local is free: its spent_before reports the subscription month, as in Phase 3
            spent_actual, open_worst, n_open = month_to_date(
                base, month, "subscription" if local else billing)
    except Exception as e:
        refuse("ledger unreadable for the ceiling check: %s" % e, cap_usd=cap)
    spent_before = round(spent_actual + open_worst, 6)
    # A $0 worst case adds nothing to the month, so a free seat is never
    # refused on dollars (an unreadable ledger above still refuses).
    if tokens:
        if spent_before + worst_tokens > pacing:
            refuse("monthly token pacing: month-to-date %d + worst case %d = %d tokens > %s.monthly_pacing_tokens %d" % (
                       spent_before, worst_tokens, spent_before + worst_tokens, cls, pacing),
                   billing=billing, meter="tokens", worst_tokens=worst_tokens,
                   spent_before_tokens=int(spent_before), pacing_tokens=pacing, month=month)
    elif not local and spent_before + worst > ceiling:
        refuse("%smonthly ceiling: month-to-date $%.2f + worst case $%.2f = $%.2f > ceiling $%.2f" % (
                   "api " if billing == "api" else "", spent_before, worst, spent_before + worst, ceiling),
               worst_usd=worst, spent_before_usd=spent_before, ceiling_usd=ceiling,
               month=month, cap_usd=cap, billing=billing, meter=meter)

    line = {"t": t0, "round": name, "seat": seat, "phase": "planned",
            "worst_usd": worst, "spent_before_usd": spent_before,
            "call_id": call_id, "cap_usd": cap, "cli_budget_usd": cli_budget,
            "reserve_usd": reserve, "ceiling_usd": ceiling, "month": month,
            "open_planned": n_open, "est_prompt_tokens": est_in,
            "max_out_tokens": max_out, "approval": approval_ref,
            "approver": approver, "scope": scope}
    if local:
        line.update(seat_class="local", max_in_tokens=max_in, cli_budget_usd=None, reserve_usd=None)
    if tokens:
        line.update(seat_class=cls, max_in_tokens=max_in, cli_budget_usd=None, reserve_usd=None,
                    worst_usd=None, spent_before_usd=None, ceiling_usd=None, cap_usd=None,
                    worst_tokens=worst_tokens, spent_before_tokens=int(spent_before),
                    pacing_tokens=pacing)
    if prices:
        line.update(seat_class=cls, max_in_tokens=max_in, cli_budget_usd=None, reserve_usd=None,
                    price_in_per_mtok_usd=prices[0], price_out_per_mtok_usd=prices[1],
                    price_per_call_usd=prices[2], price_source=prices[3])
    line.update(billing=billing, meter=meter)        # Phase 5 keys (absent on pre-012 lines: see line_class)
    try:
        append_line(base, line)
    except Exception as e:
        print("REFUSED planned line could not be written: %s" % e); sys.exit(6)
    # Phase 3: the seat is a 7th field, appended so the first six keep their places.
    # 026b: scope and approval appended as fields 8 and 9 (the first seven keep their places).
    print("PLAN %s %.2f %.2f %d %d %s %s %s" % (call_id, cli_budget, worst, max_out, autocompact, seat,
                                                 scope if widened else "confined", appr_tag))

# ---------- actual ----------

def actual(base, name, meta_rel, call_id, worst):
    try:
        with open(os.path.join(base, meta_rel)) as f: m = json.load(f)
    except Exception as e:
        print("ledger: NOT written (no readable meta: %s)" % type(e).__name__); sys.exit(4)
    # Phase 5: the billing class and meter come from the meta (new adapters
    # write them) or, for pre-012 adapters, from the seat; either way they
    # must agree with the registry. Only a SUBSCRIPTION seat may be metered
    # in tokens with no dollar figure; an api seat with no dollars fails closed.
    billing, meter = line_class(m)
    try:
        _, sreg = seat_by_ledger(load_registry(base), m.get("seat"))
    except Exception as e:
        print("ledger: NOT written (seats/registry.json unusable: %s)" % e); sys.exit(4)
    if sreg is None or (sreg["billing"], sreg["meter"]) != (billing, meter):
        print("ledger: NOT written (seat %r billing/meter %s/%s does not match the registry)" % (
            m.get("seat"), billing, meter)); sys.exit(4)
    tokens = meter == "tokens"
    api_extra = {}
    unreported = False
    if billing == "api":
        # Phase 6: the dollars must be tokens x the registry prices, exactly.
        ok, why, prices = api_prices(sreg)
        if not ok:
            print("ledger: NOT written (%s)" % why); sys.exit(4)
        it, ot, c = m.get("in_tokens"), m.get("out_tokens"), m.get("cost_usd")
        # Task 016b, MODERATOR'S RULE (jev ONLY): a SystemOne reply with no
        # usable usage is billed at the planned worst case with NULL tokens
        # (tokens are never guessed). Accepted only for seat jev, only with this
        # exact cost_source, only when cost_usd equals the planned worst case
        # and the price_source matches the registry. Every other seat, and any
        # other shape of jev meta, falls through to the exact check below.
        if m.get("seat") == "jev" and m.get("cost_source") == "unreported-billed-at-worst-case":
            if it is not None or ot is not None or not _price(c) \
                    or abs(float(c) - float(worst)) > 1e-9 or m.get("price_source") != prices[3]:
                print("ledger: NOT written (jev unreported-usage meta must carry null tokens, "
                      "cost_usd equal to the planned worst case and the registry price_source)"); sys.exit(4)
            unreported = True
            api_extra = {"price_source": prices[3], "price_in_per_mtok_usd": prices[0],
                         "price_out_per_mtok_usd": prices[1], "price_per_call_usd": prices[2],
                         "billing_rule": "moderator-unreported-worst-case"}
        elif not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in (it, ot)) \
                or not _price(c):
            print("ledger: NOT written (api meta missing integer tokens or cost_usd)"); sys.exit(4)
        if not unreported:
            if m.get("price_source") != prices[3] or abs(api_cost(prices, it, ot) - float(c)) > 1e-6:
                print("ledger: NOT written (api cost_usd/price_source does not match tokens x registry prices)"); sys.exit(4)
            api_extra = {"price_source": prices[3], "price_in_per_mtok_usd": prices[0],
                         "price_out_per_mtok_usd": prices[1], "price_per_call_usd": prices[2]}
    if tokens and billing != "subscription":
        print("ledger: NOT written (a %s seat must report dollars)" % billing); sys.exit(4)
    need = ("model", "finished") + (() if unreported else ("in_tokens", "out_tokens")) \
        + (() if tokens else ("cost_usd",))
    missing = [k for k in need if m.get(k) is None]
    if missing:
        print("ledger: NOT written (missing %s)" % ",".join(missing)); sys.exit(4)
    if tokens and (m.get("cost_usd") is not None or m.get("cost_source") != "not-reported-tokens-only"):
        print("ledger: NOT written (token seat meta carries a dollar figure or wrong cost_source)"); sys.exit(4)
    line = {"t": m["finished"], "round": name, "seat": m.get("seat"), "phase": "actual",
            "in_tokens": m["in_tokens"], "out_tokens": m["out_tokens"], "cost_usd": m.get("cost_usd"),
            "cost_source": m.get("cost_source"), "model": m["model"], "exit": m.get("exit"),
            "meta": meta_rel, "call_id": call_id, "worst_usd": None if tokens else float(worst),
            "billing": billing, "meter": meter}
    line.update(api_extra)
    if tokens and m.get("model_source"):
        line["model_source"] = m["model_source"]
    # Phase 3: a seat that reports an input-cap overage carries it onto the
    # ledger line (the local seat always reports true/false). Claude lines
    # have no such key in their meta, so their shape is unchanged.
    if "cap_exceeded" in m:
        if not isinstance(m["cap_exceeded"], bool):
            print("ledger: NOT written (cap_exceeded not true/false)"); sys.exit(4)
        line["cap_exceeded"] = m["cap_exceeded"]
    append_line(base, line)
    if tokens:
        msg = "ledger: appended (%s, %d in + %d out tokens, no dollar figure: %s)" % (
            meta_rel, m["in_tokens"], m["out_tokens"], m.get("cost_source"))
    else:
        msg = "ledger: appended (%s, $%s %s, worst case $%.2f)" % (meta_rel, m["cost_usd"], m.get("cost_source"), float(worst))
    if line.get("cap_exceeded"):
        msg += " WARNING: cap_exceeded (%s)" % m.get("cap_exceeded_detail", "input over local.max_in_tokens")
    if not tokens and float(m["cost_usd"]) > float(worst):
        msg += " WARNING: actual EXCEEDS planned worst case; the overshoot reserve is too small"
    print(msg)

# ---------- summary (Phase 5) ----------

def summary(base, month=None):
    """One line per tally. The billing classes are NEVER added together."""
    month = month or now_iso()[:7]
    if not re.fullmatch(r"\d{4}-\d\d", month):
        print("summary: bad month %r" % month); sys.exit(2)
    try:
        b = load_budget(os.path.join(base, "budget.yaml"))
        reg = load_registry(base)
        ceiling = need_num(b, "monthly_ceiling_usd")
        api_ceiling = b.get("api_monthly_ceiling_usd")
        sub_usd = month_to_date(base, month, "subscription")
        api_usd = month_to_date(base, month, "api")
        loc = [0, 0]                      # local: calls and tokens, $0
        lp = os.path.join(base, "ledger.jsonl")
        for raw in (open(lp) if os.path.exists(lp) else []):
            if not raw.strip(): continue
            j = json.loads(raw)
            if str(j.get("t", ""))[:7] == month and j.get("phase") == "actual" and line_class(j)[0] == "local":
                loc[0] += 1; loc[1] += int(j.get("in_tokens") or 0) + int(j.get("out_tokens") or 0)
        tok = []
        for sid, s in reg["seats"].items():
            if s["meter"] == "tokens":
                pace = b.get(s["token_class"], {}).get("monthly_pacing_tokens")
                tok.append((s["ledger_seat"], pace, month_to_date(base, month, s["billing"], s["ledger_seat"], "tokens")))
        apis = [(s["ledger_seat"], s["status"], month_to_date(base, month, "api", s["ledger_seat"]))
                for s in reg["seats"].values() if s["billing"] == "api"]
    except Exception as e:
        print("summary: cannot compute (%s)" % e); sys.exit(4)
    def usd(t): return "actual $%.2f + open planned $%.2f (%d open) = $%.2f" % (t[0], t[1], t[2], t[0] + t[1])
    print("ledger summary %s: billing classes are separate tallies and are NEVER added together" % month)
    print("subscription usd (pacing, notional CLI figures): %s of monthly_ceiling_usd $%.2f" % (usd(sub_usd), ceiling))
    for seat, pace, t in tok:
        print("subscription tokens %s (no dollar figure reported): actual %d + open planned %d (%d open) = %d of monthly_pacing_tokens %s" % (
            seat, t[0], t[1], t[2], t[0] + t[1], pace if pace is not None else "UNSET"))
    print("api usd (real dollars): %s of api_monthly_ceiling_usd %s" % (
        usd(api_usd), "$%.2f" % api_ceiling if isinstance(api_ceiling, (int, float)) else "UNSET"))
    for seat, status, t in apis:
        print("  api usd seat %s (%s): %s" % (seat, status, usd(t)))
    print("local (free, $0): %d calls, %d tokens actual" % (loc[0], loc[1]))
    print(moderator_line(base))

def moderator_line(base):
    """026b: every moderator approval on file (last record per task), so Dan can spot-check."""
    d = os.path.join(base, "approvals-moderator")
    items = []
    if os.path.isdir(d) and not os.path.islink(d):
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".jsonl"): continue
            try:
                for raw in open(os.path.join(d, fn)).read().splitlines():
                    if raw.strip():
                        r = json.loads(raw)
                        items.append("%s %s" % (r.get("name", fn[:-6]), str(r.get("t", "?"))[:10]))
            except Exception:
                items.append("%s UNREADABLE" % fn[:-6])
    return "moderator approvals on file (build-read only, all months): %s" % (
        "; ".join(items) if items else "none")

# ---------- grant (026b) ----------

NEVER_GRANTED = ("approvals", "approvals-moderator", "secrets")

def grant(base, home, out):
    """build-read for the claude seat: read the enumerated paths, write only work/."""
    base, home = os.path.realpath(base), os.path.realpath(home)
    dirs, files = [], []
    for e in sorted(os.listdir(base)):
        p = os.path.join(base, e)
        if e in NEVER_GRANTED or e == "work" or "\n" in e or os.path.islink(p): continue
        (dirs if os.path.isdir(p) else files).append(p)
    proj = os.path.join(home, ".claude", "projects")
    if os.path.isdir(proj): dirs.append(proj)
    allow = ["Edit(/%s/**)" % os.path.join(base, "work")]
    allow += ["Read(/%s/**)" % d for d in dirs] + ["Read(/%s)" % f for f in files]
    deny = []
    for e in NEVER_GRANTED:
        p = os.path.join(base, e)
        deny += ["Read(/%s)" % p, "Read(/%s/**)" % p, "Edit(/%s)" % p, "Edit(/%s/**)" % p]
    deny += ["Edit(/%s/**)" % d for d in dirs] + ["Edit(/%s)" % f for f in files]
    deny += ["Edit(/%s)" % base]
    cfg = {"permissions": {"allow": allow, "deny": deny},
           "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": False, "allowUnsandboxedCommands": False}}
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=1)
    for d in dirs: print(d)

# ---------- project (task 033): read-only budget projection meter ----------
# Reads budget.yaml, seats/registry.json and ledger.jsonl; writes NOTHING.
# Units follow the billing class (subscription TOKENS, api USD, local free)
# and the classes are never added together: no total of any kind is formed.

PROJECT_TOP_KEYS = ("ruleset", "rounds", "seats")
PROJECT_SEAT_KEYS = ("seat", "roles", "calls")
PROJECT_RULESETS = ("factory", "saint")

def _plan_scalar(v, where):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    if v.startswith("["):
        if not v.endswith("]"):
            raise ValueError("%s: unterminated [ list" % where)
        inner = v[1:-1].strip()
        return [] if not inner else [_plan_scalar(x, where) for x in inner.split(",")]
    if re.fullmatch(r"-?\d+", v): return int(v)
    if re.fullmatch(r"[A-Za-z0-9_.\-]+", v): return v
    raise ValueError("%s: value %r not understood" % (where, v[:40]))

def parse_plan_yaml(text):
    """The plan schema only: top-level scalars, `seats:` as a block list of
    mappings, `roles:` inline [a, b] or as an indented `- x` block list.
    Anything else is refused (fail closed)."""
    out, seats, cur, cur_list = {}, None, None, None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        where = "plan line %d" % n
        if "\t" in raw:
            raise ValueError("%s: tabs not allowed" % where)
        ind = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if ind == 0:
            m = re.fullmatch(r"([a-z_]+):(?: +(\S.*))?", body)
            if not m: raise ValueError("%s not understood" % where)
            k, v = m.groups()
            if k in out: raise ValueError("%s: key %s repeated" % (where, k))
            if k == "seats" and v is None:
                seats = out["seats"] = []; cur = cur_list = None
            elif v is None:
                raise ValueError("%s: key %s has no value" % (where, k))
            else:
                out[k] = _plan_scalar(v, where); seats = None
            continue
        if seats is None:
            raise ValueError("%s: indented line outside seats:" % where)
        m = re.fullmatch(r"- +([a-z_]+):(?: +(\S.*))?", body)
        if m:                                   # new seat item
            cur = {}; seats.append(cur); cur_list = None; item_ind = ind
            k, v = m.groups()
        else:
            m2 = re.fullmatch(r"- +(\S.*)", body)
            if m2 and cur_list is not None and ind > key_ind:
                cur_list.append(_plan_scalar(m2.group(1), where)); continue
            m = re.fullmatch(r"([a-z_]+):(?: +(\S.*))?", body)
            if not m or cur is None or ind != item_ind + 2:
                raise ValueError("%s not understood" % where)
            k, v = m.groups()
        if k in cur: raise ValueError("%s: key %s repeated" % (where, k))
        key_ind = ind if not body.startswith("-") else ind + 2
        if v is None:
            cur[k] = cur_list = []
        else:
            cur[k] = _plan_scalar(v, where); cur_list = None
    return out

def load_plan(path, reg):
    """(plan) or raise ValueError with a human message. YAML or JSON."""
    try:
        with open(path) as f:
            text = f.read()
    except OSError as e:
        raise ValueError("plan file unreadable (%s)" % type(e).__name__)
    if text.lstrip().startswith("{"):
        try:
            plan = json.loads(text)
        except ValueError as e:
            raise ValueError("plan JSON not valid (%s)" % e)
    else:
        plan = parse_plan_yaml(text)
    if not isinstance(plan, dict):
        raise ValueError("plan is not a mapping")
    extra = set(plan) - set(PROJECT_TOP_KEYS)
    miss = [k for k in PROJECT_TOP_KEYS if k not in plan]
    if extra or miss:
        raise ValueError("plan keys: missing %s, unknown %s" % (miss or "none", sorted(extra) or "none"))
    if plan["ruleset"] not in PROJECT_RULESETS:
        raise ValueError("ruleset %r not recognised (factory|saint)" % (plan["ruleset"],))
    r = plan["rounds"]
    if isinstance(r, bool) or not isinstance(r, int) or r < 1:
        raise ValueError("rounds must be a positive integer")
    if not isinstance(plan["seats"], list) or not plan["seats"]:
        raise ValueError("seats must be a non-empty list")
    seen = set()
    for i, s in enumerate(plan["seats"], 1):
        if not isinstance(s, dict) or set(s) != set(PROJECT_SEAT_KEYS):
            raise ValueError("seat entry %d must have exactly seat, roles, calls" % i)
        if not isinstance(s["seat"], str) or s["seat"] not in reg["seats"]:
            why = " (a CANDIDATE, not a seat)" if s["seat"] in reg.get("candidates", {}) else ""
            raise ValueError("seat %r unknown to seats/registry.json%s" % (s["seat"], why))
        if s["seat"] in seen:
            raise ValueError("seat %s listed twice" % s["seat"])
        seen.add(s["seat"])
        if not isinstance(s["roles"], list) or not s["roles"] or \
                not all(isinstance(x, str) and re.fullmatch(r"[a-z_]+", x) for x in s["roles"]):
            raise ValueError("seat %s: roles must be a non-empty list of names" % s["seat"])
        c = s["calls"]
        if isinstance(c, bool) or not isinstance(c, int) or c < 1:
            raise ValueError("seat %s: calls must be a positive integer" % s["seat"])
    return plan

def seat_history(base, ledger_seat, billing):
    """Comparable actual calls for one ledger seat: (scope, [(tokens, usd), ...]).
    Session calls (meta under sessions/) are preferred; if there are none, all
    of the seat's actual calls are used (scope "all")."""
    rows = []
    path = os.path.join(base, "ledger.jsonl")
    if os.path.exists(path):
        with open(path) as f:
            for raw in f:
                if not raw.strip(): continue
                j = json.loads(raw)                 # corrupt ledger raises: refused
                if j.get("phase") != "actual" or j.get("seat") != ledger_seat: continue
                ti, to = j.get("in_tokens"), j.get("out_tokens")
                if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (ti, to)):
                    continue
                usd = j.get("cost_usd")
                if billing == "api" and not isinstance(usd, (int, float)):
                    continue
                rows.append((str(j.get("meta", "")).startswith("sessions/"), ti + to, usd))
    sess = [(t, u) for s, t, u in rows if s]
    if sess:
        return "session", sess
    return "all", [(t, u) for _, t, u in rows]

def project_compute(base, plan_path):
    b = load_budget(os.path.join(base, "budget.yaml"))
    reg = load_registry(base)
    plan = load_plan(plan_path, reg)
    rs = plan["ruleset"]
    session_cap = need_num(b, rs + ".session_cap_usd")
    seats = []
    for p in plan["seats"]:
        s = reg["seats"][p["seat"]]
        billing, calls = s["billing"], p["calls"]
        row = {"seat": p["seat"], "roles": list(p["roles"]), "calls": calls,
               "billing_class": billing, "status": s["status"]}
        if billing == "local":
            row.update(unit="free", expected=None, worst_case=None,
                       expected_source="free", history_n=0, history_scope=None)
            seats.append(row); continue
        cls = s["token_class"]
        max_in = need_num(b, cls + ".max_in_tokens")
        max_out = need_num(b, cls + ".max_out_tokens")
        if billing == "subscription":
            unit = "tokens"
            worst = int(max_in + max_out) * calls          # preflight's worst_tokens per call
        else:
            unit = "usd"
            ok, why, prices = api_prices(s)
            if not ok:
                raise ValueError("seat %s: %s" % (p["seat"], why))
            per = math.ceil(round(api_cost(prices, max_in, max_out) * 100, 6)) / 100
            worst = round(per * calls, 2)                  # preflight's api worst_usd per call
        scope, hist = seat_history(base, s["ledger_seat"], billing)
        if hist:
            if unit == "tokens":
                expected = int(round(sum(t for t, _ in hist) / len(hist) * calls))
            else:
                expected = round(sum(u for _, u in hist) / len(hist) * calls, 4)
            src, n = "history", len(hist)
        else:
            expected, src, n, scope = worst, "cap-bound", 0, None
        row.update(unit=unit, expected=expected, worst_case=worst,
                   expected_source=src, history_n=n, history_scope=scope)
        seats.append(row)
    month = now_iso()[:7]
    ceil_rep = need_num(b, "monthly_ceiling_usd")
    ceil_api = need_num(b, "api_monthly_ceiling_usd")
    rep = month_to_date(base, month, "subscription")
    api = month_to_date(base, month, "api")
    def ceiling(c, t):
        mtd = round(t[0] + t[1], 4)
        return {"ceiling_usd": c, "month_to_date_usd": mtd, "actual_usd": round(t[0], 4),
                "open_planned_usd": round(t[1], 4), "open_planned_n": t[2],
                "headroom_usd": round(c - mtd, 4)}
    return {"ruleset": rs, "rounds": plan["rounds"], "session_cap_usd": session_cap,
            "seats": seats,
            "ceilings": {"month": month, "api": ceiling(ceil_api, api),
                         "reported": ceiling(ceil_rep, rep)},
            "generated_at": now_iso()}

PROJECT_CLASS_HEAD = {
    "subscription": "subscription seats (TOKENS; no dollar figure)",
    "api": "api seats (USD, real dollars)",
    "local": "local seats (free)"}

def project_text(pj):
    out = ["budget projection: ruleset %s, %d round(s). Billing classes are separate "
           "and are NEVER added together." % (pj["ruleset"], pj["rounds"])]
    for cls in BILLING:
        rows = [r for r in pj["seats"] if r["billing_class"] == cls]
        if not rows: continue
        out.append("")
        out.append(PROJECT_CLASS_HEAD[cls])
        for r in rows:
            who = "  %s [%s] x%d calls" % (r["seat"], ",".join(r["roles"]), r["calls"])
            if cls == "local":
                out.append("%s: free" % who); continue
            fmt = (lambda v: "%d tokens" % v) if r["unit"] == "tokens" else (lambda v: "$%.4f" % v)
            if r["expected_source"] == "cap-bound":
                src = "CAP-BOUND (no history; expected = worst case)"
            else:
                src = "history n=%d (%s calls)" % (r["history_n"], r["history_scope"])
            out.append("%s: expected %s, worst case %s; %s" % (who, fmt(r["expected"]), fmt(r["worst_case"]), src))
    c = pj["ceilings"]
    out.append("")
    out.append("context (%s):" % c["month"])
    out.append("  session cap (%s): $%.2f" % (pj["ruleset"], pj["session_cap_usd"]))
    out.append("  api monthly ceiling $%.2f: month-to-date $%.2f, headroom $%.2f" % (
        c["api"]["ceiling_usd"], c["api"]["month_to_date_usd"], c["api"]["headroom_usd"]))
    out.append("  reported monthly ceiling $%.2f: month-to-date $%.2f, headroom $%.2f" % (
        c["reported"]["ceiling_usd"], c["reported"]["month_to_date_usd"], c["reported"]["headroom_usd"]))
    return "\n".join(out)

def project(args):
    """budget.py project <planfile> [--json] [--base DIR]. Output only on success."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    want_json, pos, i = False, [], 0
    while i < len(args):
        if args[i] == "--json": want_json = True
        elif args[i] == "--base" and i + 1 < len(args): base = args[i + 1]; i += 1
        elif args[i].startswith("--"):
            print("project: unknown option %r" % args[i], file=sys.stderr); sys.exit(2)
        else: pos.append(args[i])
        i += 1
    if len(pos) != 1:
        print("usage: budget.py project <planfile> [--json] [--base DIR]", file=sys.stderr); sys.exit(2)
    try:
        pj = project_compute(base, pos[0])
        text = json.dumps(pj, indent=1) if want_json else project_text(pj)
    except Exception as e:
        print("project: REFUSED: %s" % e, file=sys.stderr); sys.exit(3)
    print(text)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["preflight"] and len(a) in (4, 5):
        preflight(*a[1:])
    elif a[:1] == ["actual"] and len(a) == 6:
        actual(*a[1:])
    elif a[:1] == ["summary"] and len(a) in (2, 3):
        summary(*a[1:])
    elif a[:1] == ["grant"] and len(a) == 4:
        grant(*a[1:])
    elif a[:1] == ["project"]:
        project(a[1:])
    else:
        print(__doc__); sys.exit(2)
