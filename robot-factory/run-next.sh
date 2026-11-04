#!/usr/bin/env bash
# Robot Factory seat runner v0.3: work the oldest queued task, headless.
# 009b (2026-10-31): the runner first re-executes from a private copy of
# itself (below), so a seat editing run-next.sh mid-run cannot corrupt the
# running script; and every per-call file carries the call's stamp:
# logs/<name>@<YYYYmmddTHHMMSS+-zzzz>.meta.json and .log, the same instant
# as the call_id <name>@<date -Is>. logs/<name>.log is append-only: each
# call's log is appended to it when the call ends (never truncated).
if [ "${RUN_NEXT_PRIVATE:-}" != "$0" ]; then
  _priv=$(mktemp "${TMPDIR:-/tmp}/run-next.XXXXXX") || { echo "run-next: mktemp failed"; exit 1; }
  cp -- "$0" "$_priv" || { rm -f "$_priv"; echo "run-next: cannot copy $0"; exit 1; }
  RUN_NEXT_PRIVATE=$_priv exec bash "$_priv" "$@"
  rm -f "$_priv"; echo "run-next: exec failed"; exit 1
fi
_priv=$RUN_NEXT_PRIVATE; export -n RUN_NEXT_PRIVATE; unset RUN_NEXT_PRIVATE
trap 'rm -f "$_priv"' EXIT
# Scope gate (2026-10-31, Dan's ruling): a task file containing a line
# "SCOPE: build" runs widened: the factory tree and the local usage
# records are added to the seat's access and Bash is pre-approved, so
# build tasks can install and verify their own work. Tasks without the
# marker run exactly as v0 did: confined to work/, acceptEdits, no Bash.
# Phase 1 (2026-10-31, task 003b): the call goes through
# seats/claude_code.sh in queue mode. Each run writes its per-call meta
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
# Phase 5 (2026-11-01, task 012): "SEAT: codex" and "SEAT: gemini_cli" run
# on seats/codex.sh / seats/gemini_cli.sh: subscription seats that report
# tokens but no dollar figure. Pre-flight checks their token pacing (not
# dollars), the planned and actual lines carry billing/meter, and SCOPE: build
# widens nothing (word-only). Seats come from seats/registry.json.
# Phase 6 (2026-11-01, task 014): "SEAT: jev|deepseek|perplexity|gemini_api|grok"
# run on seats/<id>.sh (api seats, real dollars, key file in secrets/ only).
# Pre-flight checks key file -> prices -> worst case vs cap and
# api_monthly_ceiling_usd; awaiting-key seats are refused. Word-only.
# Task 026b (2026-11-02): tiered scope approval. Pre-flight (bin/budget.py)
# reads the SCOPE tier and checks its approval: build-read = Dan's or the
# moderator's (approvals-moderator/), build-write and legacy SCOPE: build =
# Dan only. Its PLAN line carries scope + approval (fields 8, 9); the log
# says "approval: dan <epoch>" or "approval: moderator <epoch>". build-read
# on the claude seat gets an enumerated read grant (logs/<name>@<stamp>.grant.json,
# never approvals/, approvals-moderator/ or secrets/), writes only in work/,
# no pre-approved Bash, and permission prompts off (anything unlisted is
# denied). build-write keeps the pre-026b widened grant. RF_SEAT_RUN=1 is
# exported to every seat; bin/moderator_approve.py refuses to run under it.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
BASE="$HOME/robot-factory"
task=$(ls "$BASE/queue"/*.md 2>/dev/null | sort | head -1)
if [ -z "${task:-}" ]; then echo "queue empty"; exit 0; fi
name=$(basename "$task" .md)
# Per-call names (009b): one instant gives the call_id time and the file
# stamp. A taken stamp (same task, same second) waits for the next second.
for _try in 1 2 3 4 5; do
  _now=$(date +%s)
  t0=$(date -d "@$_now" -Is); stamp=$(date -d "@$_now" +%Y%m%dT%H%M%S%z)
  meta_rel="logs/$name@$stamp.meta.json"; log_rel="logs/$name@$stamp.log"
  [ -e "$BASE/$meta_rel" ] || [ -L "$BASE/$meta_rel" ] || [ -e "$BASE/$log_rel" ] || [ -L "$BASE/$log_rel" ] || break
  [ "$_try" -eq 5 ] && { echo "refused: $name: $meta_rel already exists; meta is never overwritten (task left in queue/)"; exit 4; }
  sleep 1
done
LOG="$BASE/$log_rel"
( set -C; : > "$LOG" ) 2>/dev/null || { echo "refused: $name: cannot create $log_rel (task left in queue/)"; exit 4; }
echo "call: $name@$t0  meta: $meta_rel  log: $log_rel" >> "$LOG"
fold_log() { cat "$LOG" >> "$BASE/logs/$name.log"; }   # per-task log: append only, never truncated
# Phase 2 pre-flight: runs on the file where it sits in queue/, before any move.
pf=$(python3 -I "$BASE/bin/budget.py" preflight "$BASE" "$task" "$name" "$t0")
prc=$?
if [ "$prc" -ne 0 ]; then
  mkdir -p "$BASE/held"
  mv "$task" "$BASE/held/$name.md"
  { echo "preflight: ${pf:-no output (rc $prc)}"
    echo "no model call made; task moved to held/"
    echo "exit=refused $(date -Is)"; } >> "$LOG"
  fold_log
  echo "refused: $name — ${pf:-preflight rc $prc} — task in held/, log: logs/$name.log"
  exit 5
fi
read -r _ call_id cli_budget worst max_out autocompact seat scope approval <<< "$pf"
case "${scope:-}" in confined|build-read|build-write) ;; *) scope=confined;; esac
export RF_SEAT_RUN=1
mv "$task" "$BASE/working/$name.md"
cd "$BASE/work" || exit 1
echo "preflight: $pf" >> "$LOG"
[ -n "${approval:-}" ] && [ "$approval" != "-" ] && echo "approval: ${approval%%:*} ${approval#*:}" >> "$LOG"
# word-only seats: SCOPE widens nothing (the line, if any, is noted)
declared=$(grep -m1 '^SCOPE:' "$BASE/working/$name.md" || true)
reply=$(mktemp) || exit 1
if [ "${seat:-}" = "qwen-local" ]; then
  echo "seat: qwen-local (seats/qwen_local.sh, Ollama 127.0.0.1, \$0 worst case)" >> "$LOG"
  [ -n "$declared" ] && \
    echo "scope: build ignored ($declared): the local seat has no tools, nothing is widened" >> "$LOG"
  "$BASE/seats/qwen_local.sh" --seat qwen-local \
    --prompt "$BASE/working/$name.md" --out "$reply" --meta "$BASE/$meta_rel" \
    --max-out-tokens "$max_out" \
    < /dev/null 2>> "$LOG"
  rc=$?
  [ "$rc" -eq 2 ] && echo "capped: the local seat stopped at its output cap ($max_out tokens)" >> "$LOG"
elif [ "${seat:-}" = "codex" ] || [ "${seat:-}" = "gemini-cli" ]; then
  adapter="$BASE/seats/${seat//-/_}.sh"
  echo "seat: $seat (${adapter#$BASE/}, subscription, tokens only, no dollar figure)" >> "$LOG"
  [ -n "$declared" ] && \
    echo "scope: build ignored ($declared): $seat is word-only, nothing is widened" >> "$LOG"
  "$adapter" --seat "$seat" \
    --prompt "$BASE/working/$name.md" --out "$reply" --meta "$BASE/$meta_rel" \
    --max-out-tokens "$max_out" \
    < /dev/null 2>> "$LOG"
  rc=$?
elif [ "${seat:-}" = "jev" ] || [ "${seat:-}" = "deepseek" ] || [ "${seat:-}" = "perplexity" ] \
     || [ "${seat:-}" = "gemini-api" ] || [ "${seat:-}" = "grok" ]; then
  adapter="$BASE/seats/${seat//-/_}.sh"
  echo "seat: $seat (${adapter#$BASE/}, api, real dollars, worst case \$$worst)" >> "$LOG"
  [ -n "$declared" ] && \
    echo "scope: build ignored ($declared): $seat is word-only, nothing is widened" >> "$LOG"
  "$adapter" --seat "$seat" \
    --prompt "$BASE/working/$name.md" --out "$reply" --meta "$BASE/$meta_rel" \
    --max-out-tokens "$max_out" \
    < /dev/null 2>> "$LOG"
  rc=$?
  [ "$rc" -eq 2 ] && echo "capped: $seat stopped at its output cap ($max_out tokens)" >> "$LOG"
else
scope_args=()
if [ "$scope" = "build-write" ]; then
  scope_args=(--add-dir "$BASE" "$HOME/.claude/projects" --allowedTools Bash)
  echo "scope: build-write (factory tree + usage records added, Bash allowed)" >> "$LOG"
elif [ "$scope" = "build-read" ]; then
  grant_rel="logs/$name@$stamp.grant.json"
  mapfile -t rdirs < <(python3 -I "$BASE/bin/budget.py" grant "$BASE" "$HOME" "$BASE/$grant_rel")
  if [ ! -s "$BASE/$grant_rel" ]; then
    mv "$BASE/working/$name.md" "$BASE/held/$name.md"
    { echo "scope: build-read grant could not be written; no model call made; task moved to held/"
      echo "exit=refused $(date -Is)"; } >> "$LOG"
    fold_log; rm -f "$reply"; echo "refused: $name — build-read grant failed — task in held/"; exit 5
  fi
  scope_args=(--permission-prompts none --settings "$BASE/$grant_rel")
  for d in "${rdirs[@]}"; do scope_args+=(--add-dir "$d"); done
  echo "scope: build-read (read: ${#rdirs[@]} enumerated dirs + top-level files, see $grant_rel; writes: work/ only; no Bash pre-approved; approvals/, approvals-moderator/, secrets/ denied)" >> "$LOG"
fi
"$BASE/seats/claude_code.sh" --seat claude-code --mode queue --cwd "$BASE/work" \
  --prompt "$BASE/working/$name.md" --out "$reply" --meta "$BASE/$meta_rel" \
  --max-budget-usd "$cli_budget" --max-out-tokens "$max_out" --autocompact "$autocompact" \
  -- "${scope_args[@]}" \
  < /dev/null 2>> "$LOG"
rc=$?
[ "$rc" -eq 2 ] && echo "capped: the seat stopped at its budget (\$$cli_budget to the CLI, worst case \$$worst)" >> "$LOG"
fi
cat "$reply" >> "$LOG"
[ -s "$reply" ] && [ -n "$(tail -c 1 "$reply")" ] && echo >> "$LOG"
rm -f "$reply"
mv "$BASE/working/$name.md" "$BASE/done/$name.md"
ledger_msg=$(python3 -I "$BASE/bin/budget.py" actual "$BASE" "$name" "$meta_rel" "$call_id" "$worst")
lrc=$?
echo "$ledger_msg" >> "$LOG"
echo "exit=$rc $(date -Is)" >> "$LOG"
fold_log
echo "done: $name (exit $rc) — log: $log_rel (appended to logs/$name.log) — $ledger_msg"
[ "$lrc" -eq 0 ] || exit 4
