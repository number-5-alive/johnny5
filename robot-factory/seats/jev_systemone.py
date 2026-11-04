"""Robot Factory core for the jev seat: TypeSafe SystemOne typed questions (task 016b, 2026-11-01).

Sibling of api_seat.py (openai-chat) and responses_seat.py (responses). Called
only by seats/jev.sh, which parses the args and refuses an existing --meta first.
One call = one HTTPS POST to the registry base_url (the FULL endpoint,
https://api.typesafe.ai/v1/systemone; no path is appended), word-only:

  jev_systemone.py <seat_id> <bindir> <prompt> <out> <meta> <seat> <max_out_arg> <budget.yaml> <timeout_s>

Task interface (the prompt file must carry exactly one JEV block):

  JEV-STATE:
  <free text>

  JEV-QUESTIONS:
  - Noul: <claim>
  - Score: <quantity> | <lowest level> | ... | <highest level>
  - Choice: <question> | <option> | <option> [| ...]

Everything after "JEV-QUESTIONS:" must be blank or "- " question lines.
Refused before any call (exit 3, label "malformed"): no/duplicate block, empty
state, no questions, unknown kind, a Choice with < 2 options (max 255), a Score
with < 2 or > 10 levels (a Score without levels is malformed), empty or
duplicate fields, a "|" inside a Noul claim. Size guard: the estimated
state + questions size over 30,000 tokens is refused before any call (the
documentation roundups disagree on the vendor limit: 64K vs ~32K).

Wire shape (task 016b probe 3, work/016-probe/probe3.record.json, HTTP 200):
  request  {"model": "jev-latest", "state": str,
            "questions": {"q1": {"type": "noul", "instructions": claim}, ...}}
           choice: {"type": "choice", "instructions": q, "criteria": {opt: opt, ...}}
           score:  {"type": "score",  "instructions": q, "criteria": [lowest, ..., highest]}
  reply    {"model": "jev-1.14.0", "answers": {"q1": {"type": "noul", "noul": 0.92}},
            "usage": {"input_tokens": 284, "output_tokens": 21}}          (LIVE)
           choice: {"type": "choice", "choice": key, "probabilities": {key: p}, "confidence": c}
           score:  {"type": "score", "score": x, "legend": {...}, "probabilities": {...}, "confidence": c}
  All three kinds LIVE (smoke 019b, work/jev-raw/019b-jev-verify@20261101T150856-0600.reply.json,
  fixture tests/phase8/fixtures/live019b_reply.json): choice probabilities are keyed by option
  text; score "legend" is an OBJECT {"0": lowest label, ..., "n-1": highest label} and score
  "probabilities" are keyed by the same index strings. Legend normalization (task 016d): an
  array of labels (documented) or an object keyed exactly "0".."n-1" (live) is accepted; the
  labels must be strings equal to the levels sent, in order. Wrong count, gaps, extra or
  non-canonical indices, wrong or non-string labels -> exit 4 unparsed.
  Score semantics (LIVE, task 019, logs/019-jev-smoke@20261101T150034-0600.meta.json,
  task 016c): "score" is a NUMBER on the continuous scale 0 .. n-1 over the n
  levels sent (lowest = 0), not an integer index: 019 returned 3.95 on a 5-level
  Score. Accepted: int/float (not bool), finite, 0 <= score <= n-1. Refused
  (exit 4 unparsed): out of range, non-numeric (incl. numeric strings), missing.
  Normalized position = score / (n-1); the nearest level is round-half-up.
  legend/probabilities stay optional (legend shapes: see above, task 016d).

Raw reply preservation (task 016c): on every "unparsed" exit the reply body is
saved byte-for-byte to <base>/work/jev-raw/<meta stem>.reply.json (exclusive
create, mode 600) and the path is recorded in meta "raw_reply". The body is the
vendor's response only; the key travels solely in the request Authorization
header and is never part of it. Belt and braces: if the key's bytes ever
appear in the body they are replaced with "[key]" before writing and meta
"raw_reply_key_scrubbed" is set true.

Contract (same as the other adapters): exit 0 ok | 2 capped | 3 seat error,
malformed JEV block, size guard, no/bad key file, unconfigured, or timeout | 4
unpriced-api or unparsed. meta.json is written in every case (exclusive
create, never overwritten) and --out always exists (empty on failure).

Auth: ONLY the locked key file named in the registry (secrets/jev.key, mode 600
or tighter, owned by the user, not a symlink, opened O_NOFOLLOW). Environment
variables are never consulted. The key is never logged, never written to
meta/out/stderr; any error text is scrubbed of it. Proxies disabled, redirects
refused, https required except for loopback (tests).

Dollars, primary path: cost_usd = input_tokens x price_in + output_tokens x
price_out (+ per-call fee) from the registry prices (budget.api_cost), exactly
as the other api seats.
Dollars, fallback: MODERATOR'S RULE (task 016b). When the reply carries no
usable usage, tokens are NEVER guessed: in_tokens and out_tokens are null,
cost_source is "unreported-billed-at-worst-case" and cost_usd is the pre-flight
worst case (max_in x price_in + max_out x price_out + fee, rounded UP to the
cent, the same figure budget.py preflight plans). budget.py accepts this ONLY
for seat jev with that exact cost_source and cost_usd equal to the planned
worst case.
"""
import datetime, json, math, os, signal, stat, sys, urllib.error, urllib.parse, urllib.request

sid, bindir, prompt, out, meta, seat, maxout_arg, budget_path, timeout_s = sys.argv[1:10]
sys.path.insert(0, bindir)
BASE = os.path.dirname(os.path.abspath(bindir))
KEY = None   # held only in memory, only for the request header
SHAPE = "systemone"
MAX_COMBINED_TOKENS = 30000            # size guard: state + questions (vendor limit disputed: 64K vs ~32K)
UNREPORTED = "unreported-billed-at-worst-case"   # MODERATOR'S RULE cost_source
CHOICE_MAX, SCORE_MIN, SCORE_MAX = 255, 2, 10
KINDS = {"Noul": "noul", "Score": "score", "Choice": "choice"}

def now(): return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

m = {"seat": seat, "model": None, "started": now(), "finished": None,
     "in_tokens": None, "out_tokens": None, "cost_usd": None,
     "cost_source": "computed-tokens-x-registry-price", "billing": "api",
     "meter": "usd", "exit": "error", "api_shape": SHAPE}

def scrub(text):
    text = str(text)
    if KEY:
        text = text.replace(KEY, "[key]")
    return text

def write_meta():
    m["finished"] = m["finished"] or now()
    body = scrub(json.dumps(m, indent=2))
    with open(meta, "x") as f:                  # exclusive create, never overwrite
        f.write(body + "\n")

def keep_raw(resp):
    """Save the unparsed reply body under <base>/work/jev-raw/; record the path in meta."""
    try:
        body = bytes(resp)
        if KEY and KEY.encode() in body:          # cannot happen (key is header-only); never trust it
            body = body.replace(KEY.encode(), b"[key]"); m["raw_reply_key_scrubbed"] = True
        d = os.path.join(BASE, "work", "jev-raw")
        os.makedirs(d, mode=0o700, exist_ok=True)
        stem = os.path.basename(meta)
        for suf in (".meta.json", ".json"):
            if stem.endswith(suf): stem = stem[:-len(suf)]; break
        for k in range(100):
            p = os.path.join(d, stem + ("" if k == 0 else ".%d" % k) + ".reply.json")
            try: fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError: continue
            with os.fdopen(fd, "wb") as f: f.write(body)
            m["raw_reply"] = p; m["raw_reply_bytes"] = len(body)
            return
        m["raw_reply_error"] = "no free file name"
    except Exception as e:
        m["raw_reply_error"] = scrub(type(e).__name__)

def die(code, label, why, text=""):
    m["exit"] = label
    m["error"] = scrub(why)[:400]
    with open(out, "w") as f: f.write(scrub(text))
    write_meta()
    print("%s: %s: %s" % (seat, label, scrub(why)), file=sys.stderr)
    sys.exit(code)

def is_count(x): return isinstance(x, int) and not isinstance(x, bool) and x >= 0
def is_score(x): return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
def num(x): return ("%.4f" % x).rstrip("0").rstrip(".")
def is_prob(x): return isinstance(x, (int, float)) and not isinstance(x, bool) and 0.0 <= x <= 1.0

# ---------- the JEV block ----------

class Malformed(Exception): pass

def parse_block(text):
    """-> (state, [(kind, instructions, options-or-None)]). Raises Malformed."""
    lines = text.splitlines()
    si = [i for i, l in enumerate(lines) if l.strip() == "JEV-STATE:"]
    qi = [i for i, l in enumerate(lines) if l.strip() == "JEV-QUESTIONS:"]
    if len(si) != 1 or len(qi) != 1:
        raise Malformed("need exactly one 'JEV-STATE:' line and one 'JEV-QUESTIONS:' line "
                        "(found %d and %d)" % (len(si), len(qi)))
    if si[0] > qi[0]:
        raise Malformed("'JEV-STATE:' must come before 'JEV-QUESTIONS:'")
    state = "\n".join(lines[si[0] + 1:qi[0]]).strip()
    if not state:
        raise Malformed("JEV-STATE is empty")
    qs = []
    for n, l in enumerate(lines[qi[0] + 1:], qi[0] + 2):
        if not l.strip():
            continue
        if not l.startswith("- "):
            raise Malformed("line %d after JEV-QUESTIONS is not a '- Kind: ...' question" % n)
        head, sep, rest = l[2:].partition(":")
        kind = KINDS.get(head.strip())
        if not sep or kind is None:
            raise Malformed("line %d: unknown question kind %r (Noul, Score or Choice)" % (n, head.strip()[:40]))
        fields = [f.strip() for f in rest.split("|")]
        if any(not f for f in fields):
            raise Malformed("line %d: empty field" % n)
        if kind == "noul":
            if len(fields) != 1:
                raise Malformed("line %d: a Noul is one claim with no '|'" % n)
            qs.append((kind, fields[0], None)); continue
        q, opts = fields[0], fields[1:]
        if len(set(opts)) != len(opts):
            raise Malformed("line %d: duplicate %s" % (n, "option" if kind == "choice" else "level"))
        if kind == "choice" and not (2 <= len(opts) <= CHOICE_MAX):
            raise Malformed("line %d: a Choice needs 2..%d options (got %d)" % (n, CHOICE_MAX, len(opts)))
        if kind == "score" and not (SCORE_MIN <= len(opts) <= SCORE_MAX):
            raise Malformed("line %d: a Score needs %d..%d levels, lowest first (got %d)" % (
                n, SCORE_MIN, SCORE_MAX, len(opts)))
        qs.append((kind, q, opts))
    if not qs:
        raise Malformed("JEV-QUESTIONS has no questions")
    return state, qs

def build_questions(qs):
    out_q = {}
    for i, (kind, q, opts) in enumerate(qs, 1):
        o = {"type": kind, "instructions": q}
        if kind == "choice":
            o["criteria"] = {x: x for x in opts}       # option text is both key and description
        elif kind == "score":
            o["criteria"] = list(opts)                  # lowest .. highest
        out_q["q%d" % i] = o
    return out_q

# ---------- typed answers ----------

def normalize_legend(qid, legend, opts):
    """-> the legend as a list of labels, lowest first. Raises ValueError unless it names
    exactly the levels sent, in order. Two shapes are accepted:
      array  ["No confidence", "Low", ...]                      (documented)
      object {"0": "No confidence", "1": "Low", ...}            (LIVE, smoke 019b)
    An object's keys must be exactly the index strings "0".."n-1" (no gaps, no extras,
    no "00"/" 1"/"-0" spellings); every label must be a string equal to the level sent."""
    n = len(opts)
    bad = "%s: legend does not match the %d levels sent" % (qid, n)
    if isinstance(legend, list):
        labels = legend
    elif isinstance(legend, dict):
        want = [str(i) for i in range(n)]
        if sorted(legend, key=lambda k: (len(k), k)) != want:
            raise ValueError("%s (keys %s, want %s..%s)" % (bad, sorted(legend)[:12], want[0], want[-1]))
        labels = [legend[k] for k in want]
    else:
        raise ValueError("%s (legend is a %s)" % (bad, type(legend).__name__))
    if len(labels) != n:
        raise ValueError("%s (%d labels)" % (bad, len(labels)))
    for i, (got, sent) in enumerate(zip(labels, opts)):
        if not isinstance(got, str):
            raise ValueError("%s (label %d is not a string)" % (bad, i))
        if got != sent:
            raise ValueError("%s (label %d is %r, level sent %r)" % (bad, i, got[:60], sent[:60]))
    return list(labels)

def read_answer(qid, kind, q, opts, a):
    """-> decision dict. Raises ValueError on a reply that does not fit the question sent."""
    if not isinstance(a, dict):
        raise ValueError("%s: answer is not an object" % qid)
    if a.get("type") != kind:
        raise ValueError("%s: answer type %r, question type %r" % (qid, a.get("type"), kind))
    d = {"id": qid, "type": kind, "instructions": q}
    if "confidence" in a and a["confidence"] is not None:
        if not is_prob(a["confidence"]): raise ValueError("%s: confidence not in 0..1" % qid)
        d["confidence"] = a["confidence"]
    if kind == "noul":
        p = a.get("noul")
        if not is_prob(p): raise ValueError("%s: noul probability missing or not in 0..1" % qid)
        d.update(probability=p, decision="holds" if p >= 0.5 else "does not hold")
        return d
    probs = a.get("probabilities")
    if probs is not None and not (isinstance(probs, dict) and all(is_prob(v) for v in probs.values())):
        raise ValueError("%s: probabilities is not a map of 0..1 numbers" % qid)
    if kind == "choice":
        c = a.get("choice")
        if c not in opts: raise ValueError("%s: choice %r is not one of the options sent" % (qid, c))
        if probs is not None and any(k not in opts for k in probs):
            raise ValueError("%s: probabilities name an option that was not sent" % qid)
        d.update(decision=c, probability=(probs or {}).get(c))
        if probs is not None: d["probabilities"] = probs
        return d
    # score: a number on the continuous scale 0 .. n-1 (lowest level = 0). LIVE (019: 3.95 of 4).
    s, n = a.get("score"), len(opts)
    if not is_score(s) or not 0 <= s <= n - 1:
        raise ValueError("%s: score %r is not a number on the 0..%d scale of the %d levels sent" % (qid, s, n - 1, n))
    legend = a.get("legend")
    if legend is not None:
        normalize_legend(qid, legend, opts)        # refuses any mismatch; labels then equal opts
    lv = min(n - 1, int(math.floor(s + 0.5)))      # nearest level, half rounds up
    d.update(score=s, levels=n, level=lv, decision=opts[lv], level_names=list(opts),
             position=round(s / (n - 1), 6))         # the normalized reading score/(n-1)
    if probs is not None:
        pl = [None] * n
        for k, v in probs.items():               # keyed by level text or by index (LIVE 019b: "0".."n-1")
            if k in opts: i = opts.index(k)      # (a validated legend equals opts, so no legend lookup)
            elif str(k).isdigit() and int(k) < n: i = int(k)
            else: raise ValueError("%s: probabilities key %r is not a level" % (qid, k))
            pl[i] = v
        pl = [v or 0.0 for v in pl]
        d.update(probabilities=pl, probability=pl[lv],
                 probability_weighted_position=round(sum(p * i for i, p in enumerate(pl)) / (n - 1), 6))
    return d

def score_words(d):
    """'3.95 of 4 — between High and Complete, near Complete'."""
    s, n, names = d["score"], d["levels"], d["level_names"]
    lo = min(int(math.floor(s)), n - 1)
    if s == lo: where = "exactly at %s" % names[lo]
    else:
        hi = lo + 1
        where = "between %s and %s, %s" % (names[lo], names[hi],
                "midway" if s - lo == 0.5 else "near %s" % names[d["level"]])
    return "%s of %d — %s" % (num(s), n - 1, where)

def render(decs, model_seen):
    w = ["Jev (%s) typed answers. Jev is a certainty auditor; it never grants the verified stamp." % model_seen, ""]
    for i, d in enumerate(decs, 1):
        kind = {"noul": "Noul", "choice": "Choice", "score": "Score"}[d["type"]]
        w.append("Q%d (%s): %s" % (i, kind, d["instructions"]))
        if d["type"] == "noul":
            w.append("  Decision: the claim %s." % d["decision"])
            w.append("  Probability the claim holds: %.2f" % d["probability"])
        elif d["type"] == "choice":
            w.append("  Decision: %s" % d["decision"])
            if d.get("probability") is not None:
                w.append("  Probability of that option: %.2f" % d["probability"])
        else:
            w.append("  Score: %s" % score_words(d))
            w.append("  Scale: 0 = %s .. %d = %s (%s)" % (d["level_names"][0], d["levels"] - 1,
                     d["level_names"][-1], " | ".join(d["level_names"])))
            w.append("  Nearest level: %s (level %d of %d, lowest = 1)" % (d["decision"], d["level"] + 1, d["levels"]))
            w.append("  Normalized position (score / %d), 0 = lowest .. 1 = highest: %.2f" % (d["levels"] - 1, d["position"]))
            if d.get("probability") is not None:
                w.append("  Probability of the nearest level: %.2f" % d["probability"])
            if d.get("probability_weighted_position") is not None:
                w.append("  Probability-weighted position, 0 = lowest .. 1 = highest: %.2f" % d["probability_weighted_position"])
        if d.get("confidence") is not None:
            w.append("  Jev's confidence: %.2f" % d["confidence"])
        w.append("")
    return "\n".join(w)

# --- registry, caps, prices: all refused before the key is even opened ---
try:
    import budget
    b = budget.load_budget(budget_path)
    max_in = int(budget.need_num(b, "api.max_in_tokens"))
    max_out = plan_max_out = int(budget.need_num(b, "api.max_out_tokens"))
    cpt = float(budget.need_num(b, "queue.chars_per_token"))
    reg = budget.load_registry(BASE)
    entry = reg["seats"][sid]
    tmo = int(timeout_s)
    if tmo <= 0 or cpt <= 0: raise ValueError("timeout and chars_per_token must be > 0")
except SystemExit: raise
except Exception as e:
    die(3, "error", "budget.yaml/registry/timeout unusable: %s" % e)
if entry.get("billing") != "api" or not isinstance(entry.get("api"), dict):
    die(3, "error", "registry seat %s is not an api seat" % sid)
api = entry["api"]
if maxout_arg:
    if not maxout_arg.isdigit(): die(3, "error", "bad --max-out-tokens %r" % maxout_arg)
    if int(maxout_arg) > max_out:
        die(3, "error", "--max-out-tokens %s exceeds api.max_out_tokens %d" % (maxout_arg, max_out))
    max_out = int(maxout_arg)
m.update(max_in_tokens=max_in, max_out_tokens=max_out)

ok, why, keyrel = budget.api_key_check(BASE, entry)
if not ok: die(3, "no-key", why)
ok, why, prices = budget.api_prices(entry)
if not ok: die(4, "unpriced-api", why)
m.update(price_in_per_mtok_usd=prices[0], price_out_per_mtok_usd=prices[1],
         price_per_call_usd=prices[2], price_source=prices[3])
m["worst_case_usd"] = budget.api_cost(prices, max_in, max_out)
# The planned worst case exactly as budget.py preflight computes it (api caps
# from budget.yaml, rounded UP to the cent): the MODERATOR'S RULE bill.
PLANNED_WORST = math.ceil(round(budget.api_cost(prices, max_in, plan_max_out) * 100, 6)) / 100

model, base_url, shape = entry.get("model"), api.get("base_url"), api.get("shape")
if shape != SHAPE or not isinstance(base_url, str) or not model:
    die(3, "unconfigured", "registry %s needs api.shape %s, api.base_url and model" % (sid, SHAPE))
u = urllib.parse.urlparse(base_url)
loopback = u.hostname in ("127.0.0.1", "::1", "localhost")
if u.scheme != "https" and not (u.scheme == "http" and loopback):
    die(3, "unconfigured", "api.base_url must be https (http only for loopback tests)")

try:
    with open(prompt, "rb") as f: ptext = f.read().decode("utf-8")
except Exception as e:
    die(3, "error", "prompt unreadable: %s" % type(e).__name__)
est = int(len(ptext) / cpt) + 1
if est > max_in:
    die(3, "error", "prompt ~%d tokens exceeds api.max_in_tokens %d" % (est, max_in))
try:
    state, qs = parse_block(ptext)
except Malformed as e:
    die(3, "malformed", "JEV block: %s" % e)
questions = build_questions(qs)
combined = math.ceil(len(state + json.dumps(questions, ensure_ascii=False)) / cpt)
m["jev"] = {"questions": len(qs), "kinds": [k for k, _, _ in qs], "state_chars": len(state),
            "combined_tokens_est": combined, "size_guard_tokens": MAX_COMBINED_TOKENS}
if combined > MAX_COMBINED_TOKENS:
    die(3, "size-guard", "state + questions ~%d tokens exceeds the %d-token guard "
        "(vendor limit disputed: 64K vs ~32K)" % (combined, MAX_COMBINED_TOKENS))

# --- the key: O_NOFOLLOW, fstat re-check, one line, no whitespace/control ---
try:
    fd = os.open(os.path.join(BASE, keyrel), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o177:
            die(3, "no-key", "key file %s changed under the check (mode/owner/type)" % keyrel)
        raw = os.read(fd, 4097)
    finally:
        os.close(fd)
    KEY = raw.decode("ascii").strip()
except SystemExit: raise
except Exception as e:
    die(3, "no-key", "key file %s unreadable: %s" % (keyrel, type(e).__name__))
if not KEY or len(raw) > 4096 or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in KEY):
    KEY = None
    die(3, "no-key", "key file %s is not one line of printable key text" % keyrel)

# --- the call: no proxies, no redirects, hard total timeout ---
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        raise urllib.error.URLError("redirect refused (the key is never re-sent)")

class Timeout(Exception): pass
def on_alarm(*_): raise Timeout()

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
# Exactly the fields probe 3 used; nothing else (SystemOne has no output-cap field).
body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
req = urllib.request.Request(base_url, data=body, method="POST",
                             headers={"Authorization": "Bearer " + KEY,
                                      "Content-Type": "application/json"})
signal.signal(signal.SIGALRM, on_alarm)
signal.alarm(tmo)
try:
    with opener.open(req, timeout=tmo) as r:
        resp = r.read(8 * 1024 * 1024)
    signal.alarm(0)
except Timeout:
    die(3, "timeout", "no complete reply within %ds" % tmo)
except urllib.error.HTTPError as e:
    signal.alarm(0)
    try: detail = e.read(300).decode("utf-8", "replace")
    except Exception: detail = ""
    die(3, "http-error", "HTTP %s: %s" % (e.code, detail))
except Exception as e:
    signal.alarm(0)
    die(3, "seat-error", "%s: %s" % (type(e).__name__, getattr(e, "reason", e)))

try:
    j = json.loads(resp)
    if not isinstance(j, dict): raise ValueError("reply is not an object")
except Exception as e:
    keep_raw(resp)
    die(4, "unparsed", "reply was not JSON (%s)" % type(e).__name__)
m["model"] = j.get("model") if isinstance(j.get("model"), str) and j.get("model") else model
m["model_source"] = "response" if m["model"] != model or j.get("model") == model else "registry"
m["model_requested"] = model

# --- billing first: a reply that came back was paid for, whatever its answers say ---
us = j.get("usage")
pt = us.get("input_tokens") if isinstance(us, dict) else None
ct = us.get("output_tokens") if isinstance(us, dict) else None
if is_count(pt) and is_count(ct):
    m.update(in_tokens=pt, out_tokens=ct, cost_usd=budget.api_cost(prices, pt, ct),
             usage_reported=True, cap_exceeded=ct > max_out)
else:
    # MODERATOR'S RULE (task 016b): no usable usage -> tokens are NOT guessed;
    # bill the planned worst case. budget.py accepts this only for seat jev.
    m.update(in_tokens=None, out_tokens=None, cost_usd=PLANNED_WORST, cost_source=UNREPORTED,
             usage_reported=False, cap_exceeded=False)

if j.get("error"):
    die(3, "seat-error", "vendor error: %s" % json.dumps(j["error"])[:300])
try:
    ans = j.get("answers")
    if not isinstance(ans, dict): raise ValueError("no answers map")
    extra = sorted(set(ans) - set(questions))
    if extra: raise ValueError("answers for questions not sent: %s" % ", ".join(extra)[:100])
    decs = []
    for i, (kind, q, opts) in enumerate(qs, 1):
        qid = "q%d" % i
        if qid not in ans: raise ValueError("%s: no answer" % qid)
        decs.append(read_answer(qid, kind, q, opts, ans[qid]))
except Exception as e:
    keep_raw(resp)
    die(4, "unparsed", "reply did not fit the questions sent (%s)" % e)
m["decisions"] = decs
with open(out, "w") as f: f.write(scrub(render(decs, m["model"])))
m["exit"] = "ok"; write_meta(); sys.exit(0)
