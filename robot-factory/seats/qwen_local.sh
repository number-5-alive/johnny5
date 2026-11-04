#!/usr/bin/env bash
# Robot Factory seat adapter: local qwen via Ollama (Phase 3, task 009,
# 2026-10-31). Same seat contract as seats/claude_code.sh (spec 2.2).
# Draft for Dan's review.
#
#   qwen_local.sh --prompt <file.md> --out <reply.md> --meta <meta.json>
#                 [--seat <id>] [--max-out-tokens <n>] [--temperature <t>]
#                 [--budget <budget.yaml>] [--timeout <s>]
#
# One non-streaming POST to the local Ollama /api/chat, model qwen3.6:27b
# (the same model the live laya-qwen service uses; Johnny). No tools: the
# reply is text only. Network: 127.0.0.1 only, proxies ignored. OLLAMA_URL
# is a TEST HOOK (like CLAUDE_BIN) and may change only the PORT; any host
# other than 127.0.0.1 is refused.
#
# Caps are read from budget.yaml at run time (local.max_in_tokens,
# local.max_out_tokens). Output: options.num_predict = max_out_tokens, a
# hard stop inside Ollama. --max-out-tokens may LOWER that, never raise it.
# Input: Ollama has no input cap, so prompt_eval_count is checked after the
# call; over the cap the reply still returns, but meta carries
# cap_exceeded=true (with the detail) and a warning goes to stderr. Never silent.
#
# Not sent on purpose: keep_alive (the server default is -1, shared with the
# live service; a per-request value would change its residency) and num_ctx
# (a different value forces a model reload under the live service).
# Contention with the live service is recorded in meta.timings
# (queue_wait_s = wall time minus Ollama's own total_duration), not avoided.
#
# Exit: 0 ok | 2 output cap hit (done_reason "length"; meta exit "capped")
#       3 seat error: unreachable, HTTP error, timeout, bad args
#       4 reply did not parse, or model/tokens missing (fails closed).
# meta.json is written in every case it can be. cost_usd is 0.0 with
# cost_source "local-free" ONLY when Ollama returned a parsed reply.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
SEAT=qwen-local PROMPT= OUT= META= MAXOUT= TEMP=0.2 BUDGET="$HERE/../budget.yaml" TIMEOUT_S=900
while [ $# -gt 0 ]; do
  case "$1" in
    --seat) SEAT=$2; shift 2;;   --prompt) PROMPT=$2; shift 2;;
    --out) OUT=$2; shift 2;;     --meta) META=$2; shift 2;;
    --max-out-tokens) MAXOUT=$2; shift 2;;
    --temperature) TEMP=$2; shift 2;;
    --budget) BUDGET=$2; shift 2;;
    --timeout) TIMEOUT_S=$2; shift 2;;
    *) echo "qwen_local.sh: unknown arg $1" >&2; exit 3;;
  esac
done
[ -n "$PROMPT" ] && [ -n "$OUT" ] && [ -n "$META" ] && [ -r "$PROMPT" ] \
  || { echo "qwen_local.sh: need readable --prompt, plus --out and --meta" >&2; exit 3; }
# 009b: per-call meta is never overwritten. An existing --meta path is refused
# before any model call (exit 3, file untouched); the write itself is
# exclusive-create, so a file appearing mid-call is not clobbered either.
[ -e "$META" ] || [ -L "$META" ] \
  && { echo "qwen_local.sh: --meta $META already exists; meta is never overwritten" >&2; exit 3; }

exec python3 -I - "$HERE/../bin" "$PROMPT" "$OUT" "$META" "$SEAT" "$MAXOUT" "$TEMP" "$BUDGET" "$TIMEOUT_S" \
  "${OLLAMA_URL:-http://127.0.0.1:11434}" <<'PY'
import datetime, json, re, sys, time, urllib.error, urllib.parse, urllib.request
bindir, prompt, out, meta, seat, maxout_arg, temp, budget_path, timeout_s, url = sys.argv[1:]
MODEL = "qwen3.6:27b"
SEED = 9                      # fixed seed + low temperature: stable records
def now(): return datetime.datetime.now().astimezone().isoformat(timespec="seconds")
m = {"seat": seat, "model": None, "started": now(), "finished": None,
     "in_tokens": None, "out_tokens": None, "cost_usd": None, "cost_source": "local-free",
     "exit": "error", "requested_model": MODEL, "endpoint": None, "think": False,
     "temperature": None, "seed": SEED, "num_predict": None, "max_in_tokens": None,
     "cap_exceeded": None, "done_reason": None, "timings": {}}
def write_meta():
    m["finished"] = m["finished"] or now()
    with open(meta, "x") as f:          # 009b: exclusive create, never overwrite
        json.dump(m, f, indent=2); f.write("\n")
def die(code, exit_label, why):
    m["exit"] = exit_label; m["error"] = why
    write_meta()
    open(out, "w").close()
    print("qwen_local.sh: " + why, file=sys.stderr)
    sys.exit(code)

# --- args and caps (budget.yaml at run time, via budget.py's own parser) ---
try:
    sys.path.insert(0, bindir)
    import budget
    b = budget.load_budget(budget_path)
    max_in = int(budget.need_num(b, "local.max_in_tokens"))
    max_out = int(budget.need_num(b, "local.max_out_tokens"))
except Exception as e:
    die(3, "error", "budget.yaml unusable: %s" % e)
if maxout_arg:
    if not re.fullmatch(r"[0-9]+", maxout_arg) or int(maxout_arg) <= 0:
        die(3, "error", "bad --max-out-tokens %r" % maxout_arg)
    if int(maxout_arg) > max_out:
        die(3, "error", "--max-out-tokens %s exceeds local.max_out_tokens %d" % (maxout_arg, max_out))
    max_out = int(maxout_arg)
try:
    t = float(temp)
    if not 0 <= t <= 2: raise ValueError
except ValueError:
    die(3, "error", "bad --temperature %r" % temp)
m.update(temperature=t, num_predict=max_out, max_in_tokens=max_in)
u = urllib.parse.urlsplit(url)
if u.scheme != "http" or u.hostname != "127.0.0.1" or u.path not in ("", "/") or u.query:
    die(3, "error", "endpoint %r refused: localhost (127.0.0.1) only" % url)
endpoint = "http://127.0.0.1:%d/api/chat" % (u.port or 11434)
m["endpoint"] = endpoint
try:
    text = open(prompt, encoding="utf-8").read()
    tmo = float(timeout_s)
except Exception as e:
    die(3, "error", "prompt/timeout unusable: %s" % e)

# --- the call ---
body = json.dumps({"model": MODEL, "stream": False, "think": False,
                   "messages": [{"role": "user", "content": text}],
                   "options": {"temperature": t, "seed": SEED, "num_predict": max_out}}).encode()
req = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"})
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # no proxies, ever
t0 = time.monotonic()
try:
    with opener.open(req, timeout=tmo) as r:
        raw = r.read()
except urllib.error.HTTPError as e:
    m["timings"]["wall_s"] = round(time.monotonic() - t0, 3)
    die(3, "error", "Ollama HTTP %d: %s" % (e.code, e.read()[:200].decode("utf-8", "replace")))
except Exception as e:
    m["timings"]["wall_s"] = round(time.monotonic() - t0, 3)
    label = "timeout" if "timed out" in str(e).lower() else "unreachable"
    die(3, label, "Ollama %s at %s: %s" % (label, endpoint, e))
wall = time.monotonic() - t0
m["finished"] = now()
m["timings"]["wall_s"] = round(wall, 3)

try:
    j = json.loads(raw)
    if not isinstance(j, dict): raise ValueError("not an object")
except Exception:
    die(4, "unparsed", "Ollama reply did not parse as JSON")
def num(x): return isinstance(x, int) and not isinstance(x, bool)
ns = {k: j.get(k) for k in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")}
for k, v in ns.items():
    if num(v): m["timings"][k.replace("_duration", "_s")] = round(v / 1e9, 3)
if num(ns["total_duration"]):
    m["timings"]["queue_wait_s"] = round(max(0.0, wall - ns["total_duration"] / 1e9), 3)
msg = j.get("message") if isinstance(j.get("message"), dict) else {}
reply = msg.get("content") if isinstance(msg.get("content"), str) else None
with open(out, "w") as f:
    f.write(reply or "")
m["model"] = j.get("model") if isinstance(j.get("model"), str) and j.get("model") else None
m["in_tokens"] = j["prompt_eval_count"] if num(j.get("prompt_eval_count")) else None
m["out_tokens"] = j["eval_count"] if num(j.get("eval_count")) else None
m["done_reason"] = j.get("done_reason")
missing = [k for k in ("model", "in_tokens", "out_tokens") if m[k] is None]
if missing or reply is None or j.get("done") is not True:
    missing += ([] if reply is not None else ["reply"]) + ([] if j.get("done") is True else ["done"])
    m["exit"] = "cost-missing:" + ",".join(missing)
    write_meta()
    print("qwen_local.sh: Ollama reply missing %s; failing closed" % ",".join(missing), file=sys.stderr)
    sys.exit(4)
if m["model"] != MODEL:
    die(4, "wrong-model", "Ollama answered with model %r, asked for %r" % (m["model"], MODEL))
m["cost_usd"] = 0.0                       # free seat: only once Ollama has answered
m["cap_exceeded"] = m["in_tokens"] > max_in
if m["cap_exceeded"]:
    m["cap_exceeded_detail"] = "in_tokens %d > local.max_in_tokens %d" % (m["in_tokens"], max_in)
    print("qwen_local.sh: WARNING cap_exceeded: " + m["cap_exceeded_detail"], file=sys.stderr)
m["out_cap_hit"] = m["done_reason"] == "length"
m["exit"] = "capped" if m["out_cap_hit"] else "ok"
write_meta()
sys.exit(2 if m["out_cap_hit"] else 0)
PY
