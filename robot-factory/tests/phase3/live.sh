#!/usr/bin/env bash
# Phase 3 LIVE demonstrations (task 009) against the real local Ollama
# (127.0.0.1:11434, qwen3.6:27b). Ollama is only called, never restarted or
# reconfigured. Demos 1-2 run in a throwaway sandbox (fake HOME, empty ledger);
# demo 3 is the real scribe over task 008, writing only under records/.
#   live.sh            all three
#   live.sh 1|2|3      one
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HOME/robot-factory"; SB="$HERE/live-sandbox"; FB="$SB/home/robot-factory"
want() { [ $# -eq 0 ] || [ "$WANT" = all ] || [ "$WANT" = "$1" ]; }
WANT=${1:-all}
setup() {
  rm -rf "$SB"; mkdir -p "$FB"/{queue,working,done,logs,work,seats,bin,held,approvals}
  cp "$SRC/run-next.sh" "$SRC/budget.yaml" "$SRC/approve.sh" "$FB/"
  cp "$SRC/seats/claude_code.sh" "$SRC/seats/qwen_local.sh" "$FB/seats/"
  cp "$SRC/bin/budget.py" "$SRC/bin/scribe.py" "$FB/bin/"
  printf '#!/bin/sh\necho "claude must not be called" >&2; exit 99\n' > "$SB/no-claude"
  chmod +x "$FB/run-next.sh" "$FB/seats/"*.sh "$SB/no-claude"; : > "$FB/ledger.jsonl"
}
run() { HOME="$SB/home" CLAUDE_BIN="$SB/no-claude" bash "$FB/run-next.sh"; echo "runner rc=$?"; }

if want 1; then
  echo "=== LIVE 1: end-to-end SEAT: qwen_local task through run-next.sh ==="; setup
  cat > "$FB/queue/951-live-local.md" <<'EOF'
# 951-live-local
SEAT: qwen_local

## Deliverable
In three short sentences, explain what a token budget is for when running
a language model on a schedule. Plain prose, no lists.
EOF
  run
  ls "$FB/done/"; echo "--- ledger"; cat "$FB/ledger.jsonl"; echo "--- reply"; cat "$FB/logs/951-live-local.log" | tail -20
  echo "--- meta timings"; python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["timings"], m["temperature"], m["seed"], m["num_predict"])' "$FB/logs/951.meta.json"
fi

if want 2; then
  echo "=== LIVE 2: runaway prompt, output cap ==="; setup
  cat > "$FB/queue/952-live-runaway.md" <<'EOF'
# 952-live-runaway
SEAT: qwen_local

## Deliverable
Count upward from 1 in words ("one, two, three, ...") and never stop. Do not
summarise, do not skip, do not end. Keep going for as long as you can.
EOF
  run
  echo "--- ledger"; cat "$FB/ledger.jsonl"
  python3 -I - "$FB/ledger.jsonl" <<'PY'
import json,sys; a=[json.loads(l) for l in open(sys.argv[1])][-1]
print("eval_count (out_tokens) =", a["out_tokens"], "cap =", 4000, "->", "WITHIN CAP" if a["out_tokens"] <= 4000 else "OVER CAP")
PY
  grep -E 'capped|seat:' "$FB/logs/952-live-runaway.log"
fi

if want 3; then
  echo "=== LIVE 3: scribe over 008-maps-gate-pack (real factory) ==="
  ( cd "$SRC" && python3 bin/scribe.py 008-maps-gate-pack ${FORCE:+--force} ); echo "scribe rc=$?"
  python3 -I - "$SRC/records/008-maps-gate-pack-record.md" "$SRC/ledger.jsonl" <<'PY'
import json,re,sys; r=open(sys.argv[1]).read()
sec=r.split("## 4. Ledger\n",1)[1].split("## 5.",1)[0]
got=re.search(r"```+jsonl\n(.*?)\n```+", sec, re.S).group(1).split("\n")
want=[l.rstrip("\n") for l in open(sys.argv[2]) if l.strip() and json.loads(l).get("round")=="008-maps-gate-pack"]
print("ledger lines in record:", len(got), " in ledger.jsonl:", len(want), " ->", "EXACT MATCH" if got==want else "MISMATCH")
PY
fi
