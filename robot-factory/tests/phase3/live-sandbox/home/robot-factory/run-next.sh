#!/usr/bin/env bash
# Robot Factory seat runner v0.2: work the oldest queued task, headless.
# Scope gate (2026-10-31, Dan's ruling): a task file containing a line
# "SCOPE: build" runs widened: the factory tree and the local usage
# records are added to the seat's access and Bash is pre-approved, so
# build tasks can install and verify their own work. Tasks without the
# marker run exactly as v0 did: confined to work/, acceptEdits, no Bash.
# Phase 1 (2026-10-31, task 003b): the call goes through
# seats/claude_code.sh in queue mode. Each run writes logs/NNN.meta.json
# and appends one "actual" line to ledger.jsonl. If the adapter cannot
# report model, tokens and cost, no ledger line is written, the log says
# so, and the runner exits 4 (missing cost data fails closed).
# Phase 2 (2026-10-31, task 006): before the call, bin/budget.py reads
# budget.yaml, checks approval (cap override or "APPROVAL: required"),
# the prompt size, and the monthly ceiling, then appends a "planned"
# line (worst case) to ledger.jsonl. On refusal it appends a "refused"
# line instead, the task moves to held/ untouched, no model call is
# made, and the runner exits 5. The call runs under the task's cap
# (--max-budget-usd = cap - overshoot reserve) and the per-call output
# cap; the actual line carries the same call_id as its planned line.
# Phase 3 (2026-10-31, task 009): a task carrying the exact line
# "SEAT: qwen_local" (set by Alex on Dan's commission, like SCOPE:) runs on
# seats/qwen_local.sh (local Ollama, free): pre-flight prices it at $0 and
# still writes its planned line; the local token caps apply. No SEAT line:
# the Claude seat, exactly as before. The local seat has no tools, so
# SCOPE: build widens nothing for it (the log says so).
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
BASE="$HOME/robot-factory"
task=$(ls "$BASE/queue"/*.md 2>/dev/null | sort | head -1)
if [ -z "${task:-}" ]; then echo "queue empty"; exit 0; fi
name=$(basename "$task" .md)
meta_rel="logs/${name%%-*}.meta.json"
[ -e "$BASE/$meta_rel" ] && meta_rel="logs/$name.meta.json"
if [ -e "$BASE/$meta_rel" ]; then
  echo "refused: $name: $meta_rel already exists; meta is never overwritten (task left in queue/)"
  exit 4
fi
# Phase 2 pre-flight: runs on the file where it sits in queue/, before any move.
pf=$(python3 -I "$BASE/bin/budget.py" preflight "$BASE" "$task" "$name")
prc=$?
if [ "$prc" -ne 0 ]; then
  mkdir -p "$BASE/held"
  mv "$task" "$BASE/held/$name.md"
  { echo "preflight: ${pf:-no output (rc $prc)}"
    echo "no model call made; task moved to held/"
    echo "exit=refused $(date -Is)"; } >> "$BASE/logs/$name.log"
  echo "refused: $name — ${pf:-preflight rc $prc} — task in held/, log: logs/$name.log"
  exit 5
fi
read -r _ call_id cli_budget worst max_out autocompact seat <<< "$pf"
mv "$task" "$BASE/working/$name.md"
cd "$BASE/work" || exit 1
: > "$BASE/logs/$name.log"
echo "preflight: $pf" >> "$BASE/logs/$name.log"
reply=$(mktemp) || exit 1
if [ "${seat:-}" = "qwen-local" ]; then
  echo "seat: qwen-local (seats/qwen_local.sh, Ollama 127.0.0.1, \$0 worst case)" >> "$BASE/logs/$name.log"
  grep -qx "SCOPE: build" "$BASE/working/$name.md" && \
    echo "scope: build ignored: the local seat has no tools, nothing is widened" >> "$BASE/logs/$name.log"
  "$BASE/seats/qwen_local.sh" --seat qwen-local \
    --prompt "$BASE/working/$name.md" --out "$reply" --meta "$BASE/$meta_rel" \
    --max-out-tokens "$max_out" \
    < /dev/null 2>> "$BASE/logs/$name.log"
  rc=$?
  [ "$rc" -eq 2 ] && echo "capped: the local seat stopped at its output cap ($max_out tokens)" >> "$BASE/logs/$name.log"
else
scope_args=()
if grep -qx "SCOPE: build" "$BASE/working/$name.md"; then
  scope_args=(--add-dir "$BASE" "$HOME/.claude/projects" --allowedTools Bash)
  echo "scope: build (factory tree + usage records added, Bash allowed)" >> "$BASE/logs/$name.log"
fi
"$BASE/seats/claude_code.sh" --seat claude-code --mode queue --cwd "$BASE/work" \
  --prompt "$BASE/working/$name.md" --out "$reply" --meta "$BASE/$meta_rel" \
  --max-budget-usd "$cli_budget" --max-out-tokens "$max_out" --autocompact "$autocompact" \
  -- "${scope_args[@]}" \
  < /dev/null 2>> "$BASE/logs/$name.log"
rc=$?
[ "$rc" -eq 2 ] && echo "capped: the seat stopped at its budget (\$$cli_budget to the CLI, worst case \$$worst)" >> "$BASE/logs/$name.log"
fi
cat "$reply" >> "$BASE/logs/$name.log"
[ -s "$reply" ] && [ -n "$(tail -c 1 "$reply")" ] && echo >> "$BASE/logs/$name.log"
rm -f "$reply"
mv "$BASE/working/$name.md" "$BASE/done/$name.md"
ledger_msg=$(python3 -I "$BASE/bin/budget.py" actual "$BASE" "$name" "$meta_rel" "$call_id" "$worst")
lrc=$?
echo "$ledger_msg" >> "$BASE/logs/$name.log"
echo "exit=$rc $(date -Is)" >> "$BASE/logs/$name.log"
echo "done: $name (exit $rc) — log: logs/$name.log — $ledger_msg"
[ "$lrc" -eq 0 ] || exit 4
