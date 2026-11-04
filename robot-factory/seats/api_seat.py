"""Robot Factory generic core for the api seats (Phase 6, task 014, 2026-11-01).

Called only by the thin wrappers seats/{jev,deepseek,perplexity,gemini_api,grok}.sh
(they parse the args and refuse an existing --meta first). One call = one HTTPS
POST to an OpenAI-compatible /chat/completions endpoint, word-only:

  api_seat.py <seat_id> <bindir> <prompt> <out> <meta> <seat> <max_out_arg> <budget.yaml> <timeout_s>

Contract (same as the other adapters): exit 0 ok | 2 capped | 3 seat error,
no/bad key file, unconfigured, or timeout | 4 unpriced-api, unparsed, or usage
missing. meta.json is written in every case (exclusive create, never
overwritten) and --out always exists (empty on failure).

Auth: ONLY the locked key file named in the registry (secrets/<id>.key, mode
600 or tighter, owned by the user, not a symlink). Environment variables are
never consulted. The key is never logged, never written to meta/out/stderr;
any error text is scrubbed of it. Proxies are disabled (no proxy ever sees the
key) and redirects are refused. https is required except for loopback (tests).
Dollars: cost_usd = in_tokens x price_in + out_tokens x price_out (+ per-call
fee), from the registry prices; null price = refused before any call. Tokens
come ONLY from the vendor's reported usage; no usage = exit 4, nothing guessed.
"""
import datetime, json, os, signal, stat, sys, urllib.error, urllib.parse, urllib.request

sid, bindir, prompt, out, meta, seat, maxout_arg, budget_path, timeout_s = sys.argv[1:10]
sys.path.insert(0, bindir)
BASE = os.path.dirname(os.path.abspath(bindir))
KEY = None   # held only in memory, only for the request header

def now(): return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

m = {"seat": seat, "model": None, "started": now(), "finished": None,
     "in_tokens": None, "out_tokens": None, "cost_usd": None,
     "cost_source": "computed-tokens-x-registry-price", "billing": "api",
     "meter": "usd", "exit": "error"}

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

model, base_url, shape = entry.get("model"), api.get("base_url"), api.get("shape")
if shape != "openai-chat" or not isinstance(base_url, str) or not model:
    die(3, "unconfigured", "registry %s needs api.shape openai-chat, api.base_url and model "
        "(UNVERIFIED facts are left null until Dan confirms them)" % sid)
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
body = json.dumps({"model": model, "messages": [{"role": "user", "content": ptext}],
                   "max_tokens": max_out, "stream": False}).encode()
req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, method="POST",
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
    ch = j["choices"][0]
    text = ch["message"]["content"] or ""
    finish = ch.get("finish_reason")
except Exception:
    die(4, "unparsed", "reply was not an OpenAI-shaped chat completion")
m["model"] = j.get("model") or model
m["model_source"] = "response" if j.get("model") else "registry"
us = j.get("usage")
pt = us.get("prompt_tokens") if isinstance(us, dict) else None
ct = us.get("completion_tokens") if isinstance(us, dict) else None
if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in (pt, ct)):
    die(4, "usage-missing", "vendor reported no usable usage; no cost is guessed", text)
tt = us.get("total_tokens")
if isinstance(tt, int) and tt > pt + ct:
    ct = tt - pt          # reasoning tokens billed as output but not in completion_tokens
m.update(in_tokens=pt, out_tokens=ct, cost_usd=budget.api_cost(prices, pt, ct))
if isinstance(us.get("cost"), (int, float, dict)):
    m["vendor_reported_cost"] = us["cost"]   # informational only; the ledger uses cost_usd
m["cap_exceeded"] = ct > max_out
with open(out, "w") as f: f.write(scrub(text))
if finish == "length":
    m["exit"] = "capped"; write_meta(); sys.exit(2)
m["exit"] = "ok"; write_meta(); sys.exit(0)
