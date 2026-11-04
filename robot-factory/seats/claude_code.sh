#!/usr/bin/env bash
# Robot Factory seat adapter: Claude Code CLI (Phase 1, spec 2.2 / 2.3).
# Draft for Dan's review. Installed by task 003b, 2026-10-31.
#
#   claude_code.sh --prompt <file.md> --out <reply.md> --meta <meta.json>
#                  [--seat <id>] [--mode text|queue] [--cwd <dir>]
#                  [--max-budget-usd <usd>] [--max-out-tokens <n>] [--autocompact <n>]
#                  [-- <extra claude args>]
#
# text  : spec 2.3. Every tool off, no MCP, no skills, no session saved,
#         fresh empty scratch dir as cwd, prompt on stdin. Extra args refused.
# queue : v0 behaviour. Same call v0 made (prompt as the argument, edits
#         auto-accepted, stdin from /dev/null, cwd from --cwd), plus
#         --output-format json so the reply and cost come back as data.
#         Args after -- (the runner's scope gate) pass straight through.
#
# Phase 2 (task 006, 2026-10-31): optional caps, passed by the runner from
# budget.yaml. --max-budget-usd goes to the CLI flag of the same name (live-
# tested: the CLI checks it AFTER each request, stops with subtype
# "error_max_budget_usd", so it can finish one request past it; the runner
# allows for that). --max-out-tokens sets CLAUDE_CODE_MAX_OUTPUT_TOKENS, a
# hard per-request output limit. --autocompact passes the CLI's auto-compact
# window. Token counts now come from modelUsage (complete on capped runs,
# where the top-level usage block is zeroed or partial); usage is the fallback.
#
# Exit: 0 ok | 2 capped: the CLI stopped at --max-budget-usd (meta exit "capped")
#       3 seat error or timeout | 4 reply did not parse, or model/tokens/cost
#       missing (fails closed). meta.json is written in every case it can be.
# Cost figures are the CLI's own (cost_source "cli-reported"); on the
# subscription they are notional list-price figures, recorded as reported.
# Not used on purpose: --bare (refuses OAuth, breaks the subscription
# login). There is no --max-turns flag in CLI 2.1.316.
set -u
export PATH="$HOME/.local/bin:$PATH"

SEAT=claude-code MODE=text PROMPT= OUT= META= CWD= EXTRA=() BUDGET= MAXOUT= AUTOCOMPACT=
CLAUDE=${CLAUDE_BIN:-claude}       # CLAUDE_BIN: test hook only (stub CLI)
while [ $# -gt 0 ]; do
  case "$1" in
    --seat) SEAT=$2; shift 2;;   --prompt) PROMPT=$2; shift 2;;
    --out) OUT=$2; shift 2;;     --meta) META=$2; shift 2;;
    --mode) MODE=$2; shift 2;;   --cwd) CWD=$2; shift 2;;
    --max-budget-usd) BUDGET=$2; shift 2;;
    --max-out-tokens) MAXOUT=$2; shift 2;;
    --autocompact) AUTOCOMPACT=$2; shift 2;;
    --) shift; EXTRA=("$@"); break;;
    *) echo "claude_code.sh: unknown arg $1" >&2; exit 3;;
  esac
done
[ -n "$PROMPT" ] && [ -n "$OUT" ] && [ -n "$META" ] && [ -r "$PROMPT" ] \
  || { echo "claude_code.sh: need readable --prompt, plus --out and --meta" >&2; exit 3; }
# 009b: per-call meta is never overwritten. An existing --meta path is refused
# before any model call (exit 3, file untouched); the write itself is
# exclusive-create, so a file appearing mid-call is not clobbered either.
[ -e "$META" ] || [ -L "$META" ] \
  && { echo "claude_code.sh: --meta $META already exists; meta is never overwritten" >&2; exit 3; }

case "$MODE" in
  text)
    [ ${#EXTRA[@]} -eq 0 ] || { echo "claude_code.sh: text mode takes no extra args" >&2; exit 3; }
    TIMEOUT_S=${TIMEOUT_S:-900}
    RUNDIR=$(mktemp -d) || exit 3
    trap 'rm -rf "$RUNDIR"' EXIT
    CMD=("$CLAUDE" -p --output-format json --no-session-persistence
         --permission-prompts none --tools "" --strict-mcp-config
         --disable-slash-commands)
    STDIN=$PROMPT
    ;;
  queue)
    [ -n "$CWD" ] && [ -d "$CWD" ] || { echo "claude_code.sh: queue mode needs --cwd <dir>" >&2; exit 3; }
    TIMEOUT_S=${TIMEOUT_S:-0}          # v0 had no timeout; 0 keeps it that way
    RUNDIR=$CWD
    CMD=("$CLAUDE" -p "$(cat "$PROMPT")" --output-format json
         --permission-mode acceptEdits "${EXTRA[@]}")
    STDIN=/dev/null
    ;;
  *) echo "claude_code.sh: --mode text|queue" >&2; exit 3;;
esac
if [ -n "$BUDGET" ]; then
  [[ "$BUDGET" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "claude_code.sh: bad --max-budget-usd" >&2; exit 3; }
  CMD+=(--max-budget-usd "$BUDGET")
fi
if [ -n "$AUTOCOMPACT" ] && [ "$AUTOCOMPACT" != 0 ]; then
  [[ "$AUTOCOMPACT" =~ ^[0-9]+$ ]] || { echo "claude_code.sh: bad --autocompact" >&2; exit 3; }
  CMD+=(--autocompact "$AUTOCOMPACT")
fi
ENVSET=()
if [ -n "$MAXOUT" ]; then
  [[ "$MAXOUT" =~ ^[0-9]+$ ]] || { echo "claude_code.sh: bad --max-out-tokens" >&2; exit 3; }
  ENVSET=(env CLAUDE_CODE_MAX_OUTPUT_TOKENS="$MAXOUT")
fi
[ "$TIMEOUT_S" -gt 0 ] 2>/dev/null && CMD=(timeout "$TIMEOUT_S" "${CMD[@]}")

RAW=$(mktemp) || exit 3
STARTED=$(date -Is)
( cd "$RUNDIR" && "${ENVSET[@]}" "${CMD[@]}" ) < "$STDIN" > "$RAW"
RC=$?
FINISHED=$(date -Is)

python3 -I - "$RAW" "$OUT" "$META" "$SEAT" "$STARTED" "$FINISHED" "$RC" <<'PY'
import json, sys
raw, out, meta, seat, started, finished, rc = sys.argv[1:]
rc = int(rc)
def write_meta(m):
    with open(meta, "x") as f:          # 009b: exclusive create, never overwrite
        json.dump(m, f, indent=2); f.write("\n")
m = {"seat": seat, "model": None, "started": started, "finished": finished,
     "in_tokens": None, "out_tokens": None, "cost_usd": None,
     "cost_source": "cli-reported", "exit": "error"}
try:
    with open(raw) as f: j = json.load(f)
    if not isinstance(j, dict): raise ValueError("not an object")
except Exception:
    m["exit"] = "timeout" if rc == 124 else "unparsed"
    write_meta(m)
    sys.exit(3 if rc else 4)
def num(x): return isinstance(x, (int, float)) and not isinstance(x, bool)
u = j.get("usage") if isinstance(j.get("usage"), dict) else {}
mu = j.get("modelUsage") if isinstance(j.get("modelUsage"), dict) else {}
# in_tokens = every input token the CLI reports: fresh + cache writes + cache reads.
# Phase 2: summed over modelUsage (all models, the same scope as total_cost_usd).
# On a budget stop the top-level usage block is zeroed or partial (live test).
mk = ("inputTokens", "cacheCreationInputTokens", "cacheReadInputTokens", "outputTokens")
if mu and all(isinstance(v, dict) and all(isinstance(v.get(k), int) for k in mk) for v in mu.values()):
    m["in_tokens"] = sum(v[k] for v in mu.values() for k in mk[:3])
    m["out_tokens"] = sum(v["outputTokens"] for v in mu.values())
else:
    parts = [u.get(k) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
    m["in_tokens"] = sum(parts) if all(isinstance(p, int) for p in parts) else None
    m["out_tokens"] = u.get("output_tokens") if isinstance(u.get("output_tokens"), int) else None
m["cost_usd"] = j.get("total_cost_usd") if num(j.get("total_cost_usd")) else None
m["model"] = ",".join(sorted(mu)) if mu else None    # exact id(s) the CLI reports
m["exit"] = "error" if (j.get("is_error") or rc != 0) else "ok"
if j.get("subtype") == "error_max_budget_usd":
    m["exit"] = "capped"
with open(out, "w") as f:
    f.write(j.get("result") if isinstance(j.get("result"), str) else "")
missing = [k for k in ("model", "in_tokens", "out_tokens", "cost_usd") if m[k] is None]
if missing:
    m["exit"] = "cost-missing:" + ",".join(missing)
    write_meta(m)
    sys.exit(4)                     # missing cost data fails closed
write_meta(m)
sys.exit({"ok": 0, "capped": 2}.get(m["exit"], 3))
PY
PRC=$?
rm -f "$RAW"
exit $PRC
