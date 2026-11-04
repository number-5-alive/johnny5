"""Robot Factory core for responses-shape api seats (Phase 9, task 021, 2026-11-01).

Sibling of api_seat.py (which stays the openai-chat core). Called only by a thin
wrapper (today: seats/perplexity.sh), which parses the args and refuses an
existing --meta first. One call = one HTTPS POST to <base_url>/v1/responses,
word-only:

  responses_seat.py <seat_id> <bindir> <prompt> <out> <meta> <seat> <max_out_arg> <budget.yaml> <timeout_s>

Wire shape (established by the task-021 live probes, work/021-probe/):
  request   {"model": <registry model>, "input": <prompt text>, "max_output_tokens": <max_out>}
  reply     {"object": "response", "status": "completed", "model": ...,
             "output": [{"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": ..., "annotations": [...]}]}],
             "usage": {"input_tokens": n, "output_tokens": n, "total_tokens": n, "cost": {...}}}
The answer is ONLY the concatenated output_text of assistant message items.
Citations, annotations, search results and any non-message output items are
never written to --out; their presence and counts go to meta["search"], so
search the vendor does inside its own API is recorded, not hidden.

Contract (same as the other adapters): exit 0 ok | 2 capped | 3 seat error,
no/bad key file, unconfigured, or timeout | 4 unpriced-api, unparsed, or usage
missing. meta.json is written in every case (exclusive create, never
overwritten) and --out always exists (empty on failure).

Auth: ONLY the locked key file named in the registry (secrets/<id>.key, mode
600 or tighter, owned by the user, not a symlink). Environment variables are
never consulted. The key is never logged, never written to meta/out/stderr;
any error text is scrubbed of it. Proxies are disabled and redirects are
refused. https is required except for loopback (tests).
Dollars: cost_usd = in_tokens x price_in + out_tokens x price_out + per-call
fee, from the registry prices (budget.api_cost); null price = refused before
any call. Tokens come ONLY from the vendor's reported usage (input_tokens ->
in_tokens, output_tokens -> out_tokens); no usage = exit 4, nothing guessed.
A vendor usage.cost is recorded only as vendor_reported_cost, never billed from.
"""
import datetime, json, os, signal, stat, sys, urllib.error, urllib.parse, urllib.request

sid, bindir, prompt, out, meta, seat, maxout_arg, budget_path, timeout_s = sys.argv[1:10]
sys.path.insert(0, bindir)
BASE = os.path.dirname(os.path.abspath(bindir))
KEY = None   # held only in memory, only for the request header
SHAPE = "responses"
PATH = "/v1/responses"

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

def die(code, label, why, text=""):
    m["exit"] = label
    m["error"] = scrub(why)[:400]
    with open(out, "w") as f: f.write(scrub(text))
    write_meta()
    print("%s: %s: %s" % (seat, label, scrub(why)), file=sys.stderr)
    sys.exit(code)

def is_count(x): return isinstance(x, int) and not isinstance(x, bool) and x >= 0

# --- registry, caps, prices: all refused before the key is even opened ---
try:
    import budget
    b = budget.load_budget(budget_path)
    max_in = int(budget.need_num(b, "api.max_in_tokens"))
    max_out = int(budget.need_num(b, "api.max_out_tokens"))
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
# The worst case this call can bill, from registry prices only (same formula
# budget.py preflight uses): max_in x price_in + max_out x price_out + per-call fee.
m["worst_case_usd"] = budget.api_cost(prices, max_in, max_out)

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
# Exactly the fields the probes used; nothing else (no tools, no stream).
body = json.dumps({"model": model, "input": ptext, "max_output_tokens": max_out}).encode()
req = urllib.request.Request(base_url.rstrip("/") + PATH, data=body, method="POST",
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

# --- parse: answer = assistant output_text only; everything else is counted ---
search = {"annotations": 0, "annotation_types": {}, "citations": 0, "search_results": 0,
          "other_output_items": 0, "other_output_types": {}}
def bump(d, k): d[k] = d.get(k, 0) + 1
try:
    j = json.loads(resp)
    if not isinstance(j, dict) or not isinstance(j.get("output"), list):
        raise ValueError("no output list")
    parts, n_msg = [], 0
    for item in j["output"]:
        if not isinstance(item, dict):
            raise ValueError("output item not an object")
        if item.get("type") == "message" and item.get("role") == "assistant":
            n_msg += 1
            for c in item.get("content") or []:
                if not isinstance(c, dict):
                    raise ValueError("content part not an object")
                if c.get("type") == "output_text":
                    if not isinstance(c.get("text"), str):
                        raise ValueError("output_text without text")
                    parts.append(c["text"])
                else:
                    bump(search["other_output_types"], "content:%s" % c.get("type"))
                    search["other_output_items"] += 1
                for a in c.get("annotations") or []:
                    search["annotations"] += 1
                    bump(search["annotation_types"], a.get("type") if isinstance(a, dict) else "?")
        else:
            search["other_output_items"] += 1
            bump(search["other_output_types"], str(item.get("type")))
    if n_msg == 0:
        raise ValueError("no assistant message in output")
    text = "".join(parts)
    status = j.get("status")
except Exception as e:
    die(4, "unparsed", "reply was not a responses-shaped object (%s)" % e)
for k in ("citations", "search_results"):
    v = j.get(k)
    if isinstance(v, list): search[k] = len(v)
search["present"] = bool(search["annotations"] or search["citations"] or search["search_results"]
                         or search["other_output_items"])
m["search"] = search
m["vendor_status"] = status
m["model"] = j.get("model") or model
m["model_source"] = "response" if j.get("model") else "registry"
if isinstance(j.get("id"), str): m["vendor_response_id"] = j["id"][:80]

us = j.get("usage")
pt = us.get("input_tokens") if isinstance(us, dict) else None
ct = us.get("output_tokens") if isinstance(us, dict) else None
if not (is_count(pt) and is_count(ct)):
    die(4, "usage-missing", "vendor reported no usable usage; no cost is guessed", text)
tt = us.get("total_tokens")
if is_count(tt) and tt > pt + ct:
    ct = tt - pt          # tokens billed outside output_tokens are counted as output
m.update(in_tokens=pt, out_tokens=ct, cost_usd=budget.api_cost(prices, pt, ct))
if isinstance(us.get("cost"), (int, float, dict)):
    m["vendor_reported_cost"] = us["cost"]   # informational only; the ledger uses cost_usd
m["cap_exceeded"] = ct > max_out
with open(out, "w") as f: f.write(scrub(text))
if j.get("error"):
    die(3, "seat-error", "vendor error: %s" % json.dumps(j["error"])[:300], text)
if status == "incomplete":
    m["incomplete_details"] = j.get("incomplete_details")
    m["exit"] = "capped"; write_meta(); sys.exit(2)
if status != "completed":
    die(3, "seat-error", "vendor status %r (not completed)" % status, text)
m["exit"] = "ok"; write_meta(); sys.exit(0)
