"""Robot Factory shared core for the token-metered subscription seats (Phase 5, task 012).

Called only by seats/codex.sh and seats/gemini_cli.sh (they parse the args and
refuse an existing --meta first). One call = one CLI run, word-only:

  token_seat.py <kind> <bindir> <prompt> <out> <meta> <seat> <max_out_arg> <budget.yaml> <timeout_s>

Contract (same as claude_code.sh / qwen_local.sh): exit 0 ok | 2 capped |
3 seat error, no auth, or timeout | 4 unparsed or tokens/model missing.
meta.json is written in every case (exclusive create, never overwritten),
and --out always exists (empty on failure). Tokens come ONLY from what the
CLI reports. Neither CLI reports a dollar figure, so cost_usd is always null
and cost_source "not-reported-tokens-only"; nothing is estimated.
Neither CLI has an output-cap flag: the timeout is the hard stop, and an
overage is recorded after the fact (cap_exceeded, cap_exceeded_detail).
Fail closed: API-key env vars refuse the call (these are subscription seats).
"""
import datetime, json, os, shutil, subprocess, sys, tempfile

kind, bindir, prompt, out, meta, seat, maxout_arg, budget_path, timeout_s = sys.argv[1:10]
sys.path.insert(0, bindir)

def now(): return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

m = {"seat": seat, "model": None, "started": now(), "finished": None,
     "in_tokens": None, "out_tokens": None, "cost_usd": None,
     "cost_source": "not-reported-tokens-only", "billing": "subscription",
     "meter": "tokens", "exit": "error"}

def write_meta():
    m["finished"] = m["finished"] or now()
    with open(meta, "x") as f:                  # exclusive create, never overwrite
        json.dump(m, f, indent=2); f.write("\n")

def die(code, label, why):
    m["exit"] = label
    m["error"] = str(why)[:400]
    with open(out, "w"): pass
    write_meta()
    print("%s: %s: %s" % (seat, label, why), file=sys.stderr)
    sys.exit(code)

CFG = {
    "codex": {"bin_env": "CODEX_BIN", "bin": "codex",
              "keys": ("OPENAI_API_KEY", "CODEX_API_KEY")},
    "gemini_cli": {"bin_env": "GEMINI_BIN", "bin": "gemini",
                   "keys": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI")},
}
if kind not in CFG: die(3, "error", "unknown token seat kind %r" % kind)
cfg = CFG[kind]

# --- fail closed: subscription seats never run on an API key ---
set_keys = [k for k in cfg["keys"] if os.environ.get(k)]
if set_keys:
    die(3, "api-key-refused", "%s set; this is a subscription seat, API-key use is parked" % ",".join(set_keys))

# --- caps (budget.yaml at run time) and the registry model ---
try:
    import budget
    b = budget.load_budget(budget_path)
    max_in = int(budget.need_num(b, kind + ".max_in_tokens"))
    max_out = int(budget.need_num(b, kind + ".max_out_tokens"))
    reg = budget.load_registry(os.path.dirname(os.path.abspath(bindir)))
    entry = reg["seats"][kind]
    tmo = int(timeout_s)
    if tmo <= 0: raise ValueError("timeout must be > 0")
except SystemExit: raise
except Exception as e:
    die(3, "error", "budget.yaml/registry/timeout unusable: %s" % e)
if maxout_arg:
    if not maxout_arg.isdigit(): die(3, "error", "bad --max-out-tokens %r" % maxout_arg)
    if int(maxout_arg) > max_out:
        die(3, "error", "--max-out-tokens %s exceeds %s.max_out_tokens %d" % (maxout_arg, kind, max_out))
    max_out = int(maxout_arg)
m.update(max_in_tokens=max_in, max_out_tokens=max_out)
model = entry.get("model")
if kind == "codex" and not model:
    # codex exec --json never names the model it ran; a ledger line without a
    # model fails closed, so the registry must name one (passed as -m).
    die(4, "model-missing", "codex does not report its model; set seats/registry.json codex.model first")

exe = shutil.which(os.environ.get(cfg["bin_env"]) or cfg["bin"])
if not exe: die(3, "no-cli", "%s not found on PATH" % cfg["bin"])
try:
    with open(prompt, "rb") as f: ptext = f.read()
except Exception as e:
    die(3, "error", "prompt unreadable: %s" % e)

def run(cmd, cwd, stdin=b"", t=tmo):
    try:
        p = subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, timeout=t)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % t

# --- auth pre-check (fast refusal; never reaches a model call) ---
if kind == "codex":
    rc, so, se = run([exe, "login", "status"], None, t=30)
    if rc != 0:
        die(3, "no-auth", "codex login status rc %d: %s (Dan: codex login)" % (rc, (so + se).strip()[:200]))
else:
    creds = os.path.join(os.path.expanduser("~"), ".gemini", "oauth_creds.json")
    if not os.path.isfile(creds):
        die(3, "no-auth", "no %s (Dan: run gemini once, Login with Google)" % creds)

def num(x): return isinstance(x, int) and not isinstance(x, bool)

with tempfile.TemporaryDirectory(prefix="rf-%s-" % kind) as rundir:
    m["started"] = now()
    if kind == "codex":
        lastmsg = os.path.join(rundir, ".lastmsg")
        cmd = [exe, "exec", "--json", "-", "-s", "read-only", "--ephemeral",
               "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
               "-C", rundir, "-o", lastmsg, "-m", model]
        for feat in ("shell_tool", "unified_exec", "apps", "browser_use", "browser_use_external",
                     "computer_use", "image_generation", "multi_agent", "plugins", "hooks",
                     "view_image", "tool_suggest", "memories"):
            cmd += ["--disable", feat]
        m["model"], m["model_source"] = model, "requested"
    else:
        cmd = [exe, "-p", "", "-o", "json", "--approval-mode", "plan", "--skip-trust", "-e", "none"]
        if model: cmd += ["-m", model]
    rc, so, se = run(cmd, rundir, ptext)
    m["finished"] = now()
    if rc == 124: die(3, "timeout", "no reply within %ss (the hard stop)" % tmo)

    text, usage = None, None
    if kind == "codex":
        errs, ins, cached, outs, reas, seen = [], 0, 0, 0, 0, False
        for line in so.splitlines():
            try: ev = json.loads(line)
            except Exception: continue
            if not isinstance(ev, dict): continue
            t = ev.get("type")
            if t == "turn.completed" and isinstance(ev.get("usage"), dict):
                u = ev["usage"]
                if not (num(u.get("input_tokens")) and num(u.get("output_tokens"))):
                    die(4, "unparsed", "turn.completed usage without integer tokens")
                seen = True
                ins += u["input_tokens"]; outs += u["output_tokens"]
                cached += u.get("cached_input_tokens") or 0; reas += u.get("reasoning_output_tokens") or 0
            elif t in ("error", "turn.failed"):
                errs.append(json.dumps(ev)[:200])
            elif t == "item.completed" and isinstance(ev.get("item"), dict) \
                    and ev["item"].get("type") == "agent_message" and isinstance(ev["item"].get("text"), str):
                text = ev["item"]["text"]
        if seen:
            usage = (ins, outs)
            m["tokens_detail"] = {"cached_input": cached, "reasoning_output": reas}
        if text is None and os.path.isfile(lastmsg):
            with open(lastmsg) as f: text = f.read()
        if errs and not seen:
            die(3, "error", "codex rc %d: %s" % (rc, "; ".join(errs)))
    else:
        try:
            j = json.loads(so)
            if not isinstance(j, dict): raise ValueError("not an object")
        except Exception:
            die(3 if rc else 4, "error" if rc else "unparsed",
                "gemini rc %d, output not JSON: %s" % (rc, (so or se).strip()[:200]))
        if j.get("error"):
            e = j["error"]
            lab = "no-auth" if isinstance(e, dict) and e.get("code") == 41 else "error"
            die(3, lab, "gemini rc %d: %s" % (rc, json.dumps(e)[:300]))
        text = j.get("response") if isinstance(j.get("response"), str) else None
        ms = (j.get("stats") or {}).get("models") if isinstance(j.get("stats"), dict) else None
        if isinstance(ms, dict) and ms:
            tk = [v.get("tokens") if isinstance(v, dict) else None for v in ms.values()]
            if all(isinstance(t, dict) and num(t.get("prompt")) and num(t.get("candidates")) for t in tk):
                # in = the full prompt the model read (cached included); out = candidates + thoughts.
                usage = (sum(t["prompt"] for t in tk),
                         sum(t["candidates"] + (t.get("thoughts") or 0) for t in tk))
                m["tokens_detail"] = {"cached": sum(t.get("cached") or 0 for t in tk),
                                      "thoughts": sum(t.get("thoughts") or 0 for t in tk)}
            m["model"] = ",".join(sorted(ms))           # the model(s) the CLI reports
            m["model_source"] = "cli-reported"

with open(out, "w") as f: f.write(text or "")
if usage: m["in_tokens"], m["out_tokens"] = usage
missing = [k for k in ("model", "in_tokens", "out_tokens") if m[k] is None]
if missing:
    m["exit"] = "tokens-missing:" + ",".join(missing)
    write_meta(); sys.exit(4)                      # no invented counts: fail closed
over = []
if m["in_tokens"] > max_in: over.append("in_tokens %d > %s.max_in_tokens %d" % (m["in_tokens"], kind, max_in))
if m["out_tokens"] > max_out: over.append("out_tokens %d > max_out %d" % (m["out_tokens"], max_out))
m["cap_exceeded"] = bool(over)
if over: m["cap_exceeded_detail"] = "; ".join(over)
m["exit"] = "ok" if rc == 0 else "error"
write_meta()
sys.exit(0 if rc == 0 else 3)
