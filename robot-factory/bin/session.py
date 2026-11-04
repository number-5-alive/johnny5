#!/usr/bin/env python3
"""Robot Factory sessions: rounds between seats (Phase 4, task 011, 2026-10-31).
Draft for Dan's review.

    python3 -I bin/session.py run <session-id>

Reads sessions/<session-id>/brief.md, runs the ruleset it names from
rulesets/<name>.json, and closes with a scribe record. Body-neutral: the
machine knows three step kinds (compose, critique, merge) and nothing about
any particular ruleset; Factory and SAINT differ only in their JSON.

Invariants (commission 011):
  * Every seat call goes through bin/budget.py preflight -> adapter ->
    bin/budget.py actual, the same path run-next.sh uses. One ledger.
  * Frontier calls in a session aggregate against <section>.session_cap_usd.
  * round_cap and artifact_pause_tokens are read from budget.yaml at run time.
  * Seats are word-only: Claude always in --mode text (no tools); qwen is
    text-only by construction. A brief with a SCOPE: line is refused.
  * Every version is its own file, created exclusively; nothing is overwritten.
  * Meld rule: the merger must ACCEPT or REJECT every point with a reason, or
    the session halts and no new version is written.
  * Convergence is mechanical: a critique with no points (critic's and the
    mechanical checks' together), or the round cap. No seat declares done.

Phase 7 (task 015, 2026-11-01): optional ruleset keys, all false by default,
so the Factory ruleset runs exactly as before:
  * "word_only": every seat must be word-only (Claude in --mode text, tools
    stripped; local, token and api seats are text-only by construction).
  * "standings": before every round after the first, the scribe computes a
    standings brief from the record so far (bin/scribe.py --standings, on the
    local scribe path, its own ledger lines, cost_source local-free). It goes
    into every cycle prompt as {{standings}}, labelled record-not-opinion, and
    carries no vote. Same code path at any seat count.
  * "decision_record": the scribe also files records/<sid>-decision-record.md
    (agreement, not verification). Brief may carry AGENDA: and SCRIBE: johnny.
  A brief never widens its own envelope: SCOPE, *CAP*, BUDGET*, APPROVAL, TOOLS,
  MODE and bare SEAT: lines are refused anywhere; MAX_ROUNDS may only lower
  the round cap, once.

Exit: 0 closed (converged or round cap) | 2 brief/ruleset/setup refused
      5 paused (artifact over artifact_pause_tokens) | 6 halted (see log)
"""
import datetime, json, math, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, HERE)            # -I drops the script dir from sys.path
import budget                       # noqa: E402  (load_budget, need_num, ...)

SID_RE = re.compile(r"[0-9]{3}[-a-z0-9]*")      # same shape the scribe accepts
STEPS = ("compose", "critique", "merge")         # the machine's whole vocabulary
# Seat name in a brief -> (adapter seat id, cost class, adapter script).
# Phase 5 (task 012): read from seats/registry.json via budget.load_registry
# (the Phase 3 table when the file is absent). Candidates are never seats.
# A malformed registry leaves no seats, so every brief is refused (fail closed).
try:
    SEATS = {sid: (s["ledger_seat"], s["token_class"], s["adapter"])
             for sid, s in budget.load_registry(BASE)["seats"].items()
             if s.get("adapter") and s.get("status") in budget.ROUTABLE}
    SEATS_ERR = None
except Exception as _e:
    SEATS, SEATS_ERR = {}, "seats/registry.json unusable: %s" % _e
FORBID = {"em-dash": ("\u2014", "the em dash (U+2014)"),
          "en-dash": ("\u2013", "the en dash (U+2013)")}
HEADER_KEYS = ("RULESET:", "SEAT ", "MAX_ROUNDS:", "FORBID:", "LABEL:", "AGENDA:", "SCRIBE:")
# Lines a brief may never carry, anywhere: they would widen its own envelope.
WIDEN_RE = re.compile(r"(SCOPE|[A-Z_]*CAP[A-Z_]*|BUDGET[A-Z_]*|APPROVAL|SEAT|TOOLS|MODE)\s*:")
SCRIBES = {"johnny": "qwen_local"}     # Johnny's scribe function is the local scribe path
WORD_ONLY_CLASSES = ("local", "codex", "gemini_cli", "api")   # text-only adapters by construction
FIRST_STANDINGS = "No standings yet: this is the first round, so nothing has been answered or left open."
SENTINEL = "NO SUBSTANTIVE POINTS"
MAX_POINTS = 8


class Halt(Exception):
    pass


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def xwrite(path, text):
    """Exclusive create: a file that exists is never overwritten."""
    with open(path, "x", encoding="utf-8") as f:
        f.write(text)


# ---------------- brief and ruleset ----------------

def parse_brief(text):
    lines = text.splitlines()
    for l in lines:
        if l.startswith("SCOPE:"):
            raise ValueError("brief has a SCOPE: line; session seats are word-only, no SCOPE widening")
        m = WIDEN_RE.match(l)
        if m:
            raise ValueError("brief may not carry %r; a brief cannot widen its own envelope "
                             "(per-call terms and caps are set by the session and budget.yaml)" % l[:20])
    head, i = [], 0
    while i < len(lines) and lines[i].strip():
        head.append(lines[i]); i += 1
    body = "\n".join(lines[i:]).strip()
    b = {"ruleset": None, "seats": {}, "max_rounds": None, "forbid": [], "label": None, "body": body,
         "agenda": None, "scribe": None}
    for l in head:
        if l.startswith("RULESET: "):
            if b["ruleset"]: raise ValueError("more than one RULESET line")
            b["ruleset"] = l[9:].strip()
        elif l.startswith("SEAT "):
            m = re.fullmatch(r"SEAT ([a-z_]+): ([a-z_]+)", l)
            if not m: raise ValueError("SEAT line malformed: %r" % l[:60])
            if m.group(1) in b["seats"]: raise ValueError("role %s seated twice" % m.group(1))
            if m.group(2) not in SEATS:
                raise ValueError(SEATS_ERR or "unknown seat %r" % m.group(2))
            b["seats"][m.group(1)] = m.group(2)
        elif l.startswith("MAX_ROUNDS: "):
            if not re.fullmatch(r"MAX_ROUNDS: [1-9][0-9]*", l): raise ValueError("MAX_ROUNDS malformed")
            if b["max_rounds"] is not None: raise ValueError("more than one MAX_ROUNDS line")
            b["max_rounds"] = int(l[12:])
        elif l.startswith("FORBID: "):
            for name in l[8:].split(","):
                name = name.strip()
                if name not in FORBID: raise ValueError("unknown FORBID %r" % name)
                b["forbid"].append(name)
        elif l.startswith("LABEL: "):
            b["label"] = l[7:].strip()
        elif l.startswith("AGENDA: "):
            if b["agenda"]: raise ValueError("more than one AGENDA line")
            b["agenda"] = l[8:].strip()
            if not b["agenda"]: raise ValueError("AGENDA is empty")
        elif l.startswith("SCRIBE: "):
            if b["scribe"]: raise ValueError("more than one SCRIBE line")
            if l[8:].strip() not in SCRIBES:
                raise ValueError("SCRIBE must name one of %s (the scribe path is local)" % ", ".join(sorted(SCRIBES)))
            b["scribe"] = l[8:].strip()
        else:
            raise ValueError("unknown header line %r (header = lines before the first blank line)" % l[:60])
    if not b["ruleset"] or not re.fullmatch(r"[a-z_]+", b["ruleset"]):
        raise ValueError("brief needs RULESET: <name>")
    if not b["body"]:
        raise ValueError("brief has no body")
    return b


def load_ruleset(name):
    with open(os.path.join(BASE, "rulesets", name + ".json"), encoding="utf-8") as f:
        r = json.load(f)
    for k in ("name", "budget_section", "roles", "open", "cycle", "prompts"):
        if k not in r: raise ValueError("ruleset %s lacks %r" % (name, k))
    if r["name"] != name: raise ValueError("ruleset file name and name field differ")
    for st in r["open"] + r["cycle"]:
        if st.get("step") not in STEPS: raise ValueError("unknown step %r" % st.get("step"))
        if st.get("role") not in r["roles"]: raise ValueError("step role %r not in roles" % st.get("role"))
        if st["step"] not in r["prompts"]: raise ValueError("no prompt for step %r" % st["step"])
    kinds = [s["step"] for s in r["cycle"]]
    if kinds != ["critique", "merge"]:
        # v1 cycle shape. A different cycle needs a new loop, which is new
        # machinery and would be named as such; refused rather than guessed.
        raise ValueError("cycle must be [critique, merge] in v1, got %r" % kinds)
    if [s["step"] for s in r["open"]] != ["compose"]:
        raise ValueError("open must be [compose] in v1")
    for k in ("word_only", "standings", "decision_record"):
        if not isinstance(r.get(k, False), bool):
            raise ValueError("ruleset key %r must be true or false" % k)
    return r


def render(lines, vals):
    def sub(m):
        if m.group(1) not in vals: raise ValueError("unknown prompt token {{%s}}" % m.group(1))
        return vals[m.group(1)]
    # Single pass: text substituted in (an artifact, a brief) is never re-scanned.
    return re.sub(r"\{\{(\w+)\}\}", sub, "\n".join(lines))


# ---------------- reply parsing ----------------

POINT_RE = re.compile(r"^\s*(?:[-*]\s*)?\**P(\d+)\**\s*[:.)]\**\s*(.*)$")
REC_RE = re.compile(r"^\s*(?:[-*]\s*)?\**([PM]\d+)\**\s*:\s*\**(ACCEPT|REJECT)\**\s*(?:-|:|\u2013|\u2014)\s*(.+?)\s*$")


def strip_think(t):
    return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()


def parse_critique(text):
    """-> list of point texts, [] for the sentinel. Raises Halt if neither."""
    t = strip_think(text)
    pts, cur = [], None
    for l in t.splitlines():
        m = POINT_RE.match(l)
        if m:
            cur = [m.group(2).strip()]; pts.append(cur)
        elif cur is not None and l.strip():
            cur.append(l.strip())
        else:
            cur = None
    pts = [" ".join(p).strip() for p in pts if " ".join(p).strip()]
    if pts:
        return pts[:MAX_POINTS], len(pts) > MAX_POINTS
    if SENTINEL in t.upper():
        return [], False
    raise Halt("critique did not parse: no 'P<n>:' points and no '%s' line" % SENTINEL)


def parse_merge(text, ids):
    t = strip_think(text)
    a, b = "=== MERGE RECORD ===", "=== ARTIFACT ==="
    if a not in t or b not in t or t.index(a) > t.index(b):
        raise Halt("meld rule: merge reply lacks '%s' then '%s'" % (a, b))
    rec_text = t[t.index(a) + len(a):t.index(b)]
    art = t[t.index(b) + len(b):].strip()
    got = {}
    for l in rec_text.splitlines():
        if not l.strip():
            continue
        m = REC_RE.match(l)
        if not m:
            continue
        pid = m.group(1)
        if pid in got:
            raise Halt("meld rule: point %s answered more than once" % pid)
        got[pid] = (m.group(2), m.group(3))
    missing = [i for i in ids if i not in got]
    extra = [i for i in got if i not in ids]
    if missing:
        raise Halt("meld rule: point(s) not answered: %s" % ", ".join(missing))
    if extra:
        raise Halt("meld rule: answers for points that were not raised: %s" % ", ".join(extra))
    if not art:
        raise Halt("merge reply has an empty artifact")
    return got, art


def mech_points(art, label, forbid):
    """The mechanism's own points (M-ids). The merger answers them like any other."""
    out = []
    for name in forbid:
        ch, desc = FORBID[name]
        n = art.count(ch)
        if n:
            out.append("The artifact contains %s %d time(s); the brief forbids it." % (desc, n))
    if label:
        first = art.lstrip().splitlines()[0] if art.strip() else ""
        if not first.strip().startswith(label):
            out.append("The artifact's first line must be exactly '%s'." % label)
    return out


def checks(art, label, forbid):
    first = art.lstrip().splitlines()[0].strip() if art.strip() else ""
    return {"words": len(art.split()),
            "label_first_line": bool(label) and first.startswith(label),
            "forbidden_counts": {n: art.count(FORBID[n][0]) for n in forbid}}


# ---------------- the session ----------------

class Session:
    def __init__(self, sid):
        self.sid = sid
        self.rel = os.path.join("sessions", sid)
        self.dir = os.path.join(BASE, self.rel)
        self.calls_dir = os.path.join(self.dir, "calls")
        self.n = 0
        self.last_t0 = None
        self.call_ids = []
        self.versions = []
        self.rounds = []
        self.log_path = os.path.join(self.dir, "session.log")

    def log(self, msg):
        with open(self.log_path, "a", encoding="utf-8") as f:   # append-only
            f.write("%s %s\n" % (now(), msg))

    # ---- money ----
    def session_spend(self):
        """Actual + open planned worst case, for this session's ledger lines."""
        actual, planned, closed = 0.0, {}, set()
        path = os.path.join(BASE, "ledger.jsonl")
        if os.path.exists(path):
            with open(path) as f:
                for raw in f:
                    if not raw.strip():
                        continue
                    j = json.loads(raw)            # corrupt ledger raises: fail closed
                    if j.get("round") != self.sid:
                        continue
                    if j.get("phase") == "actual":
                        actual += float(j.get("cost_usd") or 0)
                        if j.get("call_id"): closed.add(j["call_id"])
                    elif j.get("phase") == "planned" and j.get("call_id"):
                        planned[j["call_id"]] = float(j.get("worst_usd") or 0)
                    elif j.get("phase") == "reconciled" and j.get("call_id"):
                        closed.add(j["call_id"])
        return actual + sum(v for k, v in planned.items() if k not in closed)

    def unique_t0(self):
        t = now()
        while t == self.last_t0:
            time.sleep(0.2); t = now()
        self.last_t0 = t
        return t

    # ---- one seat call ----
    def call(self, role, kind, prompt):
        seat_name = self.brief["seats"][role]
        seat_id, cls, script = SEATS[seat_name]
        self.n += 1
        stem = "%02d-%s-%s" % (self.n, role, kind)
        self.last_stem = stem
        task_p = os.path.join(self.calls_dir, stem + ".task.md")
        prompt_p = os.path.join(self.calls_dir, stem + ".prompt.md")
        reply_p = os.path.join(self.calls_dir, stem + ".reply.md")
        meta_rel = os.path.join(self.rel, "calls", stem + ".meta.json")
        log_p = os.path.join(self.calls_dir, stem + ".log")
        if cls == "frontier":
            cap = self.per_call_cap
            try:
                spent = self.session_spend()
            except Exception as e:
                raise Halt("ledger unreadable for the session-cap check: %s" % e)
            if spent + cap > self.session_cap + 1e-9:
                raise Halt("session cap: session so far $%.2f + this call's cap $%.2f > session cap $%.2f"
                           % (spent, cap, self.session_cap))
            header = "CAP_USD: %.2f\n\n" % cap
        else:
            header = "SEAT: %s\n\n" % seat_name
        # The task file is what preflight reads (terms + the full prompt, so the
        # size estimate covers what the seat will get); the seat gets the prompt.
        xwrite(task_p, header + prompt)
        xwrite(prompt_p, prompt)
        t0 = self.unique_t0()
        pf = subprocess.run([sys.executable, "-I", os.path.join(HERE, "budget.py"), "preflight",
                             BASE, task_p, self.sid, t0], capture_output=True, text=True)
        out = pf.stdout.strip()
        self.log("call %s %s/%s seat=%s preflight: %s" % (stem, role, kind, seat_id, out or pf.stderr.strip()))
        if pf.returncode != 0 or not out.startswith("PLAN "):
            raise Halt("preflight refused call %s: %s" % (stem, out or pf.stderr.strip()))
        f = out.split()
        call_id, cli_budget, worst, max_out = f[1], f[2], f[3], f[4]
        self.call_ids.append(call_id)
        cmd = ["bash", os.path.join(BASE, script), "--seat", seat_id, "--prompt", prompt_p,
               "--out", reply_p, "--meta", os.path.join(BASE, meta_rel), "--max-out-tokens", max_out]
        if cls == "frontier":
            cmd += ["--mode", "text", "--max-budget-usd", cli_budget]   # word-only, always
        if self.rs.get("word_only") and cls not in WORD_ONLY_CLASSES and cmd[cmd.index("--mode") + 1] != "text":
            raise Halt("word-only ruleset: call %s would not run in text mode" % stem)
        with open(log_p, "x") as lf:
            rc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT).returncode
        # The actual line is always attempted, whatever the adapter did.
        ac = subprocess.run([sys.executable, "-I", os.path.join(HERE, "budget.py"), "actual",
                             BASE, self.sid, meta_rel, call_id, worst], capture_output=True, text=True)
        self.log("call %s adapter exit %d; %s" % (stem, rc, (ac.stdout or ac.stderr).strip()))
        if ac.returncode != 0:
            raise Halt("actual line not written for %s (exit %d); the planned line stays open at its worst case"
                       % (stem, ac.returncode))
        if rc != 0:
            raise Halt("seat %s exited %d on call %s (see calls/%s.log)" % (seat_id, rc, stem, stem))
        with open(reply_p, encoding="utf-8") as rf:
            return rf.read()

    # ---- versions ----
    def add_version(self, round_no, role, art):
        v = len(self.versions) + 1
        name = "r%d-%s-v%d.md" % (round_no, role, v)
        xwrite(os.path.join(self.dir, name), art.rstrip() + "\n")
        self.versions.append(name)
        self.log("version v%d written: %s (%d words)" % (v, name, len(art.split())))
        return v

    def current(self):
        with open(os.path.join(self.dir, self.versions[-1]), encoding="utf-8") as f:
            return f.read()

    def vals(self, art=None, points=None):
        forbid = ""
        if self.brief["forbid"]:
            forbid = "Do not use these characters anywhere in the artifact: %s." % ", ".join(
                FORBID[n][1] for n in self.brief["forbid"])
        return {"brief": self.brief["body"], "label": self.brief["label"] or "(none)",
                "forbid": forbid, "artifact": art or "", "points": points or "",
                "version": "v%d" % len(self.versions), "agenda": self.agenda,
                "standings": self.standings_text}

    def paused(self, art):
        est = math.ceil(len(art) / self.cpt)
        if est > self.pause_tokens:
            self.log("PAUSE: artifact v%d estimated %d tokens > artifact_pause_tokens %d"
                     % (len(self.versions), est, self.pause_tokens))
            return True
        return False

    # ---- run ----
    def setup(self):
        if not SID_RE.fullmatch(self.sid):
            raise ValueError("session id must match %s" % SID_RE.pattern)
        if not os.path.isfile(os.path.join(self.dir, "brief.md")):
            raise ValueError("no %s/brief.md" % self.rel)
        if os.path.exists(os.path.join(self.dir, "session.json")) or os.path.exists(self.calls_dir):
            raise ValueError("session %s has already run (session.json or calls/ exists); sessions run once" % self.sid)
        with open(os.path.join(self.dir, "brief.md"), encoding="utf-8") as f:
            self.brief = parse_brief(f.read())
        self.rs = load_ruleset(self.brief["ruleset"])
        if not self.rs.get("decision_record"):
            for k in ("agenda", "scribe"):
                if self.brief[k]:
                    raise ValueError("%s: is a decision-record header; ruleset %s has no decision record"
                                     % (k.upper(), self.rs["name"]))
        # Word-only envelope: refused at setup if any seat could run with tools.
        if self.rs.get("word_only"):
            for role, seat in sorted(self.brief["seats"].items()):
                _, cls, script = SEATS[seat]
                if not (cls in WORD_ONLY_CLASSES or (cls == "frontier" and script == "seats/claude_code.sh")):
                    raise ValueError("ruleset %s is word-only; seat %s (%s, %s) has no text-only mode"
                                     % (self.rs["name"], seat, cls, script))
        body_first = next((x.strip() for x in self.brief["body"].splitlines() if x.strip()), "")
        self.agenda = self.brief["agenda"] or body_first
        self.agenda_source = "AGENDA line" if self.brief["agenda"] else "first line of the brief body"
        self.standings_text = FIRST_STANDINGS if self.rs.get("standings") else ""
        # Capacities: one row per (seat, capacity). Roles vote; the scribe never does.
        self.capacities = [{"seat": self.brief["seats"][r], "capacity": r, "votes": True}
                           for r in self.rs["roles"] if r in self.brief["seats"]]
        if self.rs.get("decision_record") or self.rs.get("standings"):
            self.capacities.append({"seat": SCRIBES.get(self.brief["scribe"], "qwen_local"),
                                    "name": self.brief["scribe"] or None,
                                    "capacity": "scribe", "votes": False,
                                    "path": "bin/scribe.py through seats/qwen_local.sh (local)"})
        for role in self.rs["roles"]:
            if role not in self.brief["seats"]:
                raise ValueError("brief seats no one in role %r" % role)
        for role in self.brief["seats"]:
            if role not in self.rs["roles"]:
                raise ValueError("brief seats role %r, which ruleset %s does not have" % (role, self.rs["name"]))
        b = budget.load_budget(os.path.join(BASE, "budget.yaml"))
        sec = self.rs["budget_section"]
        self.session_cap = budget.need_num(b, sec + ".session_cap_usd")
        round_cap = int(budget.need_num(b, sec + ".round_cap"))
        self.pause_tokens = budget.need_num(b, "artifact_pause_tokens")
        self.cpt = budget.need_num(b, "queue.chars_per_token")
        reserve = budget.need_num(b, "queue.overshoot_reserve_usd")
        mr = self.brief["max_rounds"]
        if mr is not None and mr > round_cap:
            raise ValueError("MAX_ROUNDS %d > %s.round_cap %d; a brief may only lower it" % (mr, sec, round_cap))
        self.rounds_allowed = mr or round_cap
        frontier = lambda steps: sum(1 for s in steps if SEATS[self.brief["seats"][s["role"]]][1] == "frontier")
        self.max_frontier = frontier(self.rs["open"]) + self.rounds_allowed * frontier(self.rs["cycle"])
        self.per_call_cap = (math.floor(self.session_cap * 100 / self.max_frontier) / 100
                             if self.max_frontier else 0.0)
        if self.max_frontier and self.per_call_cap <= reserve:
            raise ValueError("per-call cap $%.2f (session cap / %d frontier calls) does not exceed the "
                             "overshoot reserve $%.2f" % (self.per_call_cap, self.max_frontier, reserve))
        os.mkdir(self.calls_dir)

    # ---- standings turn (between rounds; the scribe's, not a seat's) ----
    def standings_turn(self, r):
        """The scribe computes the state of the room from the record so far.
        Written under records/ by the scribe, copied here verbatim, and put in
        front of every seat that speaks in round r. No vote, no seat call."""
        state = {"session": self.sid, "ruleset": self.rs["name"], "before_round": r,
                 "agenda": self.agenda, "seats": self.brief["seats"], "capacities": self.capacities,
                 "steps": {st["role"]: st["step"] for st in self.rs["open"] + self.rs["cycle"]},
                 "versions": self.versions, "rounds": self.rounds}
        xwrite(os.path.join(self.dir, "r%d-state.json" % r), json.dumps(state, indent=2) + "\n")
        sc = subprocess.run([sys.executable, "-I", os.path.join(HERE, "scribe.py"), "--standings", self.sid, str(r)],
                            capture_output=True, text=True)
        self.log("standings before round %d: scribe exit %d: %s"
                 % (r, sc.returncode, (sc.stdout + sc.stderr).strip().replace("\n", " | ")))
        src = os.path.join(BASE, "records", "%s-r%d-standings.md" % (self.sid, r))
        if sc.returncode not in (0, 3) or not os.path.isfile(src):
            raise Halt("standings turn before round %d failed (scribe exit %d); no seat speaks without it"
                       % (r, sc.returncode))
        with open(src, encoding="utf-8") as f:
            text = f.read()
        name = "r%d-standings.md" % r
        xwrite(os.path.join(self.dir, name), text)
        self.standings_text = text.strip()
        return name

    def run(self):
        self.started = now()
        self.log("OPEN session %s ruleset=%s seats=%s rounds_allowed=%d (%s.round_cap read at run time) "
                 "session_cap=$%.2f frontier_calls_max=%d per_call_cap=$%.2f pause_tokens=%d"
                 % (self.sid, self.rs["name"], json.dumps(self.brief["seats"], sort_keys=True),
                    self.rounds_allowed, self.rs["budget_section"], self.session_cap,
                    self.max_frontier, self.per_call_cap, self.pause_tokens))
        status, reason = None, None
        try:
            st = self.rs["open"][0]
            reply = self.call(st["role"], "compose", render(self.rs["prompts"]["compose"], self.vals()))
            art = strip_think(reply)
            if not art:
                raise Halt("compose reply was empty")
            self.add_version(0, st["role"], art)
            crit, merg = self.rs["cycle"]
            for r in range(1, self.rounds_allowed + 1):
                art = self.current()
                if self.paused(art):
                    status, reason = "paused", "artifact over artifact_pause_tokens before round %d" % r
                    break
                sfile = self.standings_turn(r) if self.rs.get("standings") and r > 1 else None
                rnd = {"round": r, "critiqued": self.versions[-1]}
                if sfile:
                    rnd["standings"] = sfile
                self.rounds.append(rnd)
                reply = self.call(crit["role"], "critique",
                                  render(self.rs["prompts"]["critique"], self.vals(art)))
                rnd["critique_call"] = self.last_stem
                pts, trimmed = parse_critique(reply)
                mpts = mech_points(art, self.brief["label"], self.brief["forbid"])
                ids = ["P%d" % (i + 1) for i in range(len(pts))] + ["M%d" % (i + 1) for i in range(len(mpts))]
                texts = pts + mpts
                cfile = "r%d-%s-critique.md" % (r, crit["role"])
                body = ["# Round %d critique of %s" % (r, self.versions[-1]), "",
                        "Seat: %s (%s). Points renumbered P1..Pn by the session; M points are the session's mechanical checks."
                        % (crit["role"], self.brief["seats"][crit["role"]]), ""]
                body += ["%s: %s" % (i, t) for i, t in zip(ids, texts)] or [SENTINEL]
                if trimmed:
                    body += ["", "(The critic gave more than %d points; only the first %d are carried.)" % (MAX_POINTS, MAX_POINTS)]
                xwrite(os.path.join(self.dir, cfile), "\n".join(body) + "\n")
                rnd.update(critique=cfile, points=len(pts), mech_points=len(mpts),
                           raised=[{"id": i, "point": t} for i, t in zip(ids, texts)])
                self.log("round %d critique: %d critic point(s), %d mechanical point(s) -> %s"
                         % (r, len(pts), len(mpts), cfile))
                if not texts:
                    status, reason = "converged", "round %d critique returned no substantive points" % r
                    break
                plist = "\n".join("%s: %s" % (i, t) for i, t in zip(ids, texts))
                reply = self.call(merg["role"], "merge",
                                  render(self.rs["prompts"]["merge"], self.vals(art, plist)))
                rnd["merge_call"] = self.last_stem
                got, new_art = parse_merge(reply, ids)
                for p in rnd["raised"]:
                    p["decision"], p["reason"] = got[p["id"]]
                acc = [i for i in ids if got[i][0] == "ACCEPT"]
                rej = [i for i in ids if got[i][0] == "REJECT"]
                mfile = "r%d-%s-record.md" % (r, merg["role"])
                rec = ["# Round %d merge record" % r, "",
                       "Seat: %s (%s). Merged %s with %s into the next version." % (
                           merg["role"], self.brief["seats"][merg["role"]], self.versions[-1], cfile), "",
                       "| Point | Raised | Decision | Reason |", "|---|---|---|---|"]
                for i, t in zip(ids, texts):
                    cell = lambda s: s.replace("|", "\\|").replace("\n", " ")
                    rec.append("| %s | %s | %s | %s |" % (i, cell(t), got[i][0], cell(got[i][1])))
                rec += ["", "## Disagreements (rejected points, surfaced not blended)", ""]
                rec += ["- %s: %s  \n  Rejected because: %s" % (i, texts[ids.index(i)], got[i][1]) for i in rej] or ["None: every point was accepted."]
                xwrite(os.path.join(self.dir, mfile), "\n".join(rec) + "\n")
                v = self.add_version(r, merg["role"], new_art)
                rnd.update(record=mfile, accepted=acc, rejected=rej,
                           disagreements=[{"id": i, "point": texts[ids.index(i)], "reason": got[i][1]} for i in rej],
                           produced=self.versions[-1])
                self.log("round %d merge: %d accepted, %d rejected (%s) -> %s, v%d"
                         % (r, len(acc), len(rej), ", ".join(rej) or "none", mfile, v))
            else:
                status, reason = "round_cap", "round cap %d reached" % self.rounds_allowed
            if status == "round_cap" and self.paused(self.current()):
                status, reason = "paused", "final artifact over artifact_pause_tokens"
        except Halt as e:
            status, reason = "halted", str(e)
            self.log("HALT: %s" % e)
        except FileExistsError as e:
            status, reason = "halted", "refused to overwrite %s" % e.filename
            self.log("HALT: %s" % reason)
        return self.close(status, reason)

    def close(self, status, reason):
        final = self.versions[-1] if self.versions else None
        fc = None
        if final:
            fc = checks(self.current(), self.brief["label"], self.brief["forbid"])
        rec = {"session": self.sid, "ruleset": self.rs["name"], "budget_section": self.rs["budget_section"],
               "seats": self.brief["seats"], "status": status, "stop_reason": reason,
               "started": self.started, "closed": now(), "rounds_allowed": self.rounds_allowed,
               "session_cap_usd": self.session_cap, "per_call_cap_usd": self.per_call_cap,
               "versions": self.versions, "rounds": self.rounds, "call_ids": self.call_ids,
               "final_version": final, "final_checks": fc,
               "label": "Outputs are drafts. No seat declared this work done; the session stopped by rule.",
               "word_only": bool(self.rs.get("word_only")), "standings": bool(self.rs.get("standings")),
               "decision_record": bool(self.rs.get("decision_record")),
               "agenda": self.agenda, "agenda_source": self.agenda_source,
               "scribe": self.brief["scribe"], "capacities": self.capacities,
               "steps": {st["role"]: st["step"] for st in self.rs["open"] + self.rs["cycle"]},
               "costs": "in ledger.jsonl only (round == session id)"}
        xwrite(os.path.join(self.dir, "session.json"), json.dumps(rec, indent=2) + "\n")
        self.log("CLOSE status=%s reason=%s final=%s checks=%s"
                 % (status, reason, final, json.dumps(fc, sort_keys=True)))
        self.log("recording: python3 -I bin/scribe.py --session %s" % self.sid)
        sc = subprocess.run([sys.executable, "-I", os.path.join(HERE, "scribe.py"), "--session", self.sid],
                            capture_output=True, text=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write("%s scribe exit %d: %s\n" % (now(), sc.returncode, (sc.stdout + sc.stderr).strip().replace("\n", " | ")))
        print("session %s: %s (%s); final %s; scribe exit %d" % (self.sid, status, reason, final, sc.returncode))
        return {"converged": 0, "round_cap": 0, "paused": 5}.get(status, 6)


def main(argv):
    if len(argv) != 2 or argv[0] != "run":
        print(__doc__.split("\n\n")[1]); return 2
    s = Session(argv[1])
    try:
        s.setup()
    except Exception as e:
        print("session: REFUSED %s" % e); return 2
    return s.run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
