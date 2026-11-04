"""Phase 11 checks for `budget.py project` (task 033). Run via run-tests.sh."""
import hashlib, json, math, os, re, shutil, subprocess, sys

HERE = sys.argv[1]
SRC = os.path.dirname(os.path.dirname(HERE))          # the live factory
SB = os.path.join(HERE, "sandbox")
LOO = os.path.join(SB, "loo", "robot-factory")        # leave-one-out history
EMPTY = os.path.join(SB, "empty", "robot-factory")    # no history at all
FIX = os.path.join(HERE, "fixtures")
PLAN = os.path.join(FIX, "024s1-plan.yaml")
ROUND = "024s1-saint-economics"
RECORDED_USD = 0.3787                                 # records/024s1-...-record.md line 91
PASS = FAIL = 0

def ok(cond, label, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print("  PASS: %s" % label)
    else: FAIL += 1; print("  FAIL: %s %s" % (label, detail))

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

LIVE = [os.path.join(SRC, p) for p in ("budget.yaml", "ledger.jsonl", "seats/registry.json")]
live_before = {p: sha(p) for p in LIVE}

def build(dst, keep):
    os.makedirs(os.path.join(dst, "bin")); os.makedirs(os.path.join(dst, "seats"))
    shutil.copy(os.path.join(SRC, "bin", "budget.py"), os.path.join(dst, "bin"))
    shutil.copy(os.path.join(SRC, "budget.yaml"), dst)
    shutil.copy(os.path.join(SRC, "seats", "registry.json"), os.path.join(dst, "seats"))
    with open(os.path.join(SRC, "ledger.jsonl")) as f, open(os.path.join(dst, "ledger.jsonl"), "w") as g:
        for raw in f:
            if raw.strip() and keep(json.loads(raw)): g.write(raw)

shutil.rmtree(SB, ignore_errors=True)
build(LOO, lambda j: j.get("round") != ROUND)
build(EMPTY, lambda j: False)

def run(base, *args):
    p = subprocess.run([sys.executable, "-I", os.path.join(base, "bin", "budget.py"), "project",
                        *args, "--base", base], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

def ledger(base):
    return [json.loads(l) for l in open(os.path.join(base, "ledger.jsonl")) if l.strip()]

# ---------------------------------------------------------------- JSON contract
print("== contract: --json validity and keys")
rc, out, err = run(LOO, PLAN, "--json")
ok(rc == 0 and not err, "024s1 plan --json rc 0", "rc=%d err=%r" % (rc, err[:200]))
try:
    pj = json.loads(out); ok(True, "--json output parses")
except ValueError as e:
    pj = {}; ok(False, "--json output parses", str(e))
TOP = ("ruleset", "rounds", "session_cap_usd", "seats", "ceilings", "generated_at")
SEATK = ("seat", "roles", "calls", "billing_class", "unit", "expected", "worst_case",
         "expected_source", "history_n")
ok(all(k in pj for k in TOP), "top-level contract keys present", sorted(pj))
ok(all(all(k in s for k in SEATK) for s in pj.get("seats", [])) and pj.get("seats"),
   "every seat carries the contract keys")
ok(pj.get("ruleset") == "saint" and pj.get("rounds") == 3 and pj.get("session_cap_usd") == 6.5,
   "ruleset/rounds/session cap (saint.session_cap_usd read live)")
c = pj.get("ceilings", {})
ok(all(k in c.get(x, {}) for x in ("api", "reported") for k in ("ceiling_usd", "month_to_date_usd", "headroom_usd")),
   "ceilings api + reported carry ceiling, month-to-date, headroom")
seats = {s["seat"]: s for s in pj.get("seats", [])}
cc, cx = seats.get("claude_code", {}), seats.get("codex", {})
ok(cc.get("calls", 0) + cx.get("calls", 0) == 7, "fixture frontier calls total 7 (4 claude + 3 codex)")

# JSON plan input gives the same seats as the YAML plan
jplan = os.path.join(SB, "024s1-plan.json")
json.dump({"ruleset": "saint", "rounds": 3, "seats": [
    {"seat": "claude_code", "roles": ["proposer", "chair"], "calls": 4},
    {"seat": "codex", "roles": ["challenger"], "calls": 3}]}, open(jplan, "w"))
rc, out2, _ = run(LOO, jplan, "--json")
ok(rc == 0 and json.loads(out2)["seats"] == pj.get("seats"), "JSON plan == YAML plan")

# ---------------------------------------------------------------- P1 containment
print("== P1: containment of the recorded 024s1 cost (leave-one-out history)")
live = ledger(SRC)
act = [j for j in live if j.get("round") == ROUND and j.get("phase") == "actual"]
actual_usd = sum(float(j["cost_usd"]) for j in act if j.get("cost_usd") is not None)
ok(round(actual_usd, 4) == RECORDED_USD, "live ledger 024s1 actuals = recorded $0.3787", actual_usd)
ok(not any(j.get("round") == ROUND for j in ledger(LOO)), "sandbox history has no 024s1 line")
# conversion tokens -> USD for the claude seat. budget.py holds no per-token
# price table for subscription seats, so the suite (never the display) uses the
# history's own fitted rate: sum(cost_usd)/sum(tokens) over the same comparable
# calls the projection used (session calls, leave-one-out).
hist = [j for j in ledger(LOO) if j.get("seat") == "claude-code" and j.get("phase") == "actual"
        and str(j.get("meta", "")).startswith("sessions/")]
ok(len(hist) == cc.get("history_n") and cc.get("history_scope") == "session",
   "claude history = %d session calls (011s1), as projected" % len(hist))
rate = sum(j["cost_usd"] for j in hist) / sum(j["in_tokens"] + j["out_tokens"] for j in hist)
exp_usd = cc["expected"] * rate
# worst case in USD: the planned worst_usd the session would write per claude
# call (bin/session.py: per_call_cap = floor(session_cap*100/frontier_calls)/100)
per_call = math.floor(pj["session_cap_usd"] * 100 / cc["calls"]) / 100
worst_usd = per_call * cc["calls"]
rec_worst = sum(j["worst_usd"] for j in live if j.get("round") == ROUND and j.get("phase") == "planned"
                and j.get("worst_usd") is not None)
print("    claude: expected %d tokens x $%.8f/token = $%.4f; worst %d x $%.2f = $%.2f (recorded planned worst $%.2f)"
      % (cc["expected"], rate, exp_usd, cc["calls"], per_call, worst_usd, rec_worst))
print("    codex: $0 (token-metered, no dollar figure; recorded cost_usd null)")
ok(exp_usd <= actual_usd <= worst_usd,
   "frontier band [$%.4f expected, $%.2f worst] contains recorded $%.4f" % (exp_usd, worst_usd, actual_usd))
ok(actual_usd <= rec_worst, "also inside the recorded planned worst ($%.2f at the $5.00 cap of the day)" % rec_worst)
for seat, ls in (("claude_code", "claude-code"), ("codex", "codex")):
    s = seats[seat]
    t = sum(j["in_tokens"] + j["out_tokens"] for j in act if j["seat"] == ls)
    print("    %s tokens: expected %d, actual %d, worst %d" % (seat, s["expected"], t, s["worst_case"]))
    ok(s["expected"] <= t <= s["worst_case"], "%s token band contains the actual tokens" % seat)

# ---------------------------------------------------------------- P2 separation
print("== P2: class separation (all three classes in one plan)")
mixed = os.path.join(SB, "mixed.yaml")
open(mixed, "w").write("ruleset: factory\nrounds: 2\nseats:\n"
                       "  - seat: claude_code\n    roles: [drafter]\n    calls: 3\n"
                       "  - seat: codex\n    roles: [critic]\n    calls: 2\n"
                       "  - seat: deepseek\n    roles: [critic]\n    calls: 2\n"
                       "  - seat: grok\n    roles: [critic]\n    calls: 1\n"
                       "  - seat: qwen_local\n    roles: [scribe]\n    calls: 2\n")
rc, mj, _ = run(LOO, mixed, "--json"); rc2, mt, _ = run(LOO, mixed)
ok(rc == 0 and rc2 == 0, "mixed plan projects in both outputs")
mj = json.loads(mj)
BAD = re.compile(r"total|combined|grand|sum|overall|aggregate|all_classes", re.I)
def keys(o):
    if isinstance(o, dict):
        for k, v in o.items(): yield k; yield from keys(v)
    elif isinstance(o, list):
        for v in o: yield from keys(v)
ok(not [k for k in keys(mj) if BAD.search(k)], "no JSON key at any depth suggests a total",
   [k for k in keys(mj) if BAD.search(k)])
ok(not BAD.search(mt), "no total/combined/grand/sum word in the text output")
units = {s["billing_class"]: set() for s in mj["seats"]}
for s in mj["seats"]: units[s["billing_class"]].add(s["unit"])
ok(units == {"subscription": {"tokens"}, "api": {"usd"}, "local": {"free"}},
   "units follow billing class (subscription tokens, api usd, local free)", units)
q = [s for s in mj["seats"] if s["seat"] == "qwen_local"][0]
ok(q["expected"] is None and q["worst_case"] is None, "local: null expected and worst_case in JSON")
ok(re.search(r"qwen_local \[scribe\] x2 calls: free$", mt, re.M), "local: 'free' in text")
# class figures; no figure anywhere may equal the sum of two classes' figures
byc = {}
for s in mj["seats"]:
    for v in (s["expected"], s["worst_case"]):
        if v is not None: byc.setdefault(s["billing_class"], []).append(float(v))
cross = set()
classes = sorted(byc)
for i, a in enumerate(classes):
    for b in classes[i + 1:]:
        for x in byc[a]:
            for y in byc[b]: cross.add(round(x + y, 2))
# the same within a class across seats would also be a total: check those too
for a in classes:
    xs = byc[a]
    for i in range(len(xs)):
        for k in range(i + 1, len(xs)): cross.add(round(xs[i] + xs[k], 2))
def nums(o):
    if isinstance(o, dict):
        for v in o.values(): yield from nums(v)
    elif isinstance(o, list):
        for v in o: yield from nums(v)
    elif isinstance(o, (int, float)) and not isinstance(o, bool): yield float(o)
jsonnums = {round(v, 2) for v in nums({k: v for k, v in mj.items() if k != "ceilings"})}
tnums = {round(float(x), 2) for x in re.findall(r"\d+(?:\.\d+)?", mt.split("\ncontext")[0])}
# a seat's own figure may coincide with a cross-sum by accident; flag only
# sums that are not themselves one of the seat figures
own = {round(v, 2) for vs in byc.values() for v in vs}
ok(not ((jsonnums - own) & cross) and not (cross & jsonnums - own),
   "no JSON number is a sum of two seats' figures")
ok(not ((tnums - own) & cross), "no text figure is a sum of two seats' figures",
   sorted((tnums - own) & cross)[:5])
heads = re.findall(r"^(subscription|api|local) seats", mt, re.M)
ok(heads == ["subscription", "api", "local"], "text grouped under class headers", heads)

# ---------------------------------------------------------------- cap-bound
print("== cap-bound fallback (no history)")
rc, ej, _ = run(EMPTY, mixed, "--json"); rc2, et, _ = run(EMPTY, mixed)
ej = json.loads(ej)
cb = [s for s in ej["seats"] if s["billing_class"] != "local"]
ok(rc == 0 and all(s["expected_source"] == "cap-bound" and s["expected"] == s["worst_case"]
                   and s["history_n"] == 0 for s in cb), "JSON: every priced seat cap-bound, expected = worst")
ok(et.count("CAP-BOUND") == len(cb), "text: CAP-BOUND marked on every priced seat")
ok([s for s in mj["seats"] if s["seat"] == "claude_code"][0]["expected_source"] == "history",
   "with history the same seat is 'history'")
gp = os.path.join(SB, "gem.yaml")
open(gp, "w").write("ruleset: saint\nrounds: 1\nseats:\n  - seat: gemini_cli\n    roles: [critic]\n    calls: 2\n")
rc, gj, _ = run(LOO, gp, "--json"); g = json.loads(gj)["seats"][0]
ok(g["expected_source"] == "cap-bound" and g["expected"] == g["worst_case"] == 184000,
   "gemini_cli (never called) cap-bound in a real-history ledger: 2 x 92000 tokens")
rc, gt, _ = run(LOO, gp)
ok("CAP-BOUND" in gt, "gemini_cli cap-bound in text")

# ---------------------------------------------------------------- refusals
print("== refusals: no output, nonzero, nothing written")
SBF = [os.path.join(LOO, p) for p in ("budget.yaml", "ledger.jsonl", "seats/registry.json")]
sb_before = {p: (sha(p), os.stat(p).st_mtime_ns) for p in SBF}
bad = {
    "unknown seat": "ruleset: saint\nrounds: 1\nseats:\n  - seat: hal9000\n    roles: [chair]\n    calls: 1\n",
    "bad ruleset": "ruleset: chaos\nrounds: 1\nseats:\n  - seat: codex\n    roles: [critic]\n    calls: 1\n",
    "candidate-like unknown": "ruleset: saint\nrounds: 1\nseats:\n  - seat: claude-code\n    roles: [chair]\n    calls: 1\n",
    "zero calls": "ruleset: saint\nrounds: 1\nseats:\n  - seat: codex\n    roles: [critic]\n    calls: 0\n",
    "missing seats": "ruleset: saint\nrounds: 1\n",
    "extra key": "ruleset: saint\nrounds: 1\ntotal: 5\nseats:\n  - seat: codex\n    roles: [critic]\n    calls: 1\n",
    "garbage yaml": "ruleset: saint\nrounds: 1\nseats:\n  - seat: codex\n   roles: [critic\n",
    "bad json": '{"ruleset": "saint", "rounds": 1, "seats": [',
    "json bad ruleset": '{"ruleset": "SAINT", "rounds": 1, "seats": [{"seat": "codex", "roles": ["x"], "calls": 1}]}',
}
for name, text in bad.items():
    p = os.path.join(SB, "bad-%s.plan" % name.replace(" ", "-"))
    open(p, "w").write(text)
    for extra in ((), ("--json",)):
        rc, o, e = run(LOO, p, *extra)
        ok(rc != 0 and o == "" and "REFUSED" in e,
           "%s%s refused (rc %d, no stdout, message)" % (name, " --json" if extra else "", rc), repr(e[:120]))
rc, o, e = run(LOO, os.path.join(SB, "no-such-plan.yaml"))
ok(rc != 0 and o == "", "missing plan file refused")
ok(all((sha(p), os.stat(p).st_mtime_ns) == sb_before[p] for p in SBF),
   "sandbox ledger, budget.yaml, registry untouched by every run")

# ---------------------------------------------------------------- live untouched
rc, o, e = subprocess.run([sys.executable, "-I", os.path.join(SRC, "bin", "budget.py"), "project",
                           os.path.join(SB, "bad-unknown-seat.plan")], capture_output=True, text=True
                          ).returncode, None, None
ok(rc != 0, "live tree: malformed plan refused")
ok({p: sha(p) for p in LIVE} == live_before, "live budget.yaml, ledger.jsonl, registry unchanged")

print("phase11: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
