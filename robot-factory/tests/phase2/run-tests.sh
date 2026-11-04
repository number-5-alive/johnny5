#!/usr/bin/env bash
# Phase 2 sandbox tests (task 006). Builds a throwaway fake HOME under
# tests/phase2/sandbox/, copies the factory's Phase 2 files into it, and
# runs the real runner against a stub CLI that records every invocation.
# Fixture ledgers and fixture approvals exist ONLY in the sandbox.
# Usage: run-tests.sh <runner> <adapter>   (the staged or installed files)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HOME/robot-factory"
RUNNER=${1:-$SRC/run-next.sh}; ADAPTER=${2:-$SRC/seats/claude_code.sh}
SB="$HERE/sandbox"; FB="$SB/home/robot-factory"
pass=0; fail=0
ok()  { echo "  PASS: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }

stub() {  # stub CLI: logs argv + output cap env, emits JSON per STUB_MODE
cat > "$SB/stub-claude" <<'EOF'
#!/usr/bin/env bash
{ printf 'CALL'; for a in "$@"; do printf ' [%s]' "$(printf '%s' "$a" | tr '\n' ' ' | head -c 80)"; done; echo " MAXOUT=${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-unset}"; } >> "$STUB_CALLS"
case "${STUB_MODE:-ok}" in
  ok) echo '{"type":"result","subtype":"success","is_error":false,"result":"stub reply","total_cost_usd":0.25,"usage":{"input_tokens":5,"cache_creation_input_tokens":100,"cache_read_input_tokens":1000,"output_tokens":50},"modelUsage":{"claude-opus-5-5":{"inputTokens":5,"cacheCreationInputTokens":100,"cacheReadInputTokens":1000,"outputTokens":50,"costUSD":0.25}}}';;
  capped) echo '{"type":"result","subtype":"error_max_budget_usd","is_error":true,"errors":["Reached maximum budget"],"terminal_reason":"budget_exhausted","total_cost_usd":0.11,"usage":{"input_tokens":0,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":0},"modelUsage":{"claude-opus-5-5":{"inputTokens":6,"cacheCreationInputTokens":2756,"cacheReadInputTokens":9841,"outputTokens":463,"costUSD":0.11}}}'; exit 1;;
esac
EOF
chmod +x "$SB/stub-claude"
}

fresh() {  # new sandbox tree with an optional fixture ledger
  rm -rf "$SB"; mkdir -p "$FB"/{queue,working,done,logs,work,seats,bin,held,approvals}
  cp "$RUNNER" "$FB/run-next.sh"; cp "$ADAPTER" "$FB/seats/claude_code.sh"
  cp "$SRC/bin/budget.py" "$FB/bin/"; cp "$SRC/budget.yaml" "$FB/"; cp "$SRC/approve.sh" "$FB/"
  chmod +x "$FB/run-next.sh" "$FB/seats/claude_code.sh"
  : > "$FB/ledger.jsonl"; stub; : > "$SB/calls"
}
task() {  # task <name> [extra header lines...]
  local n=$1; shift
  { echo "# $n"; for l in "$@"; do echo "$l"; done; echo; echo "## Deliverable"; echo "sandbox test"; } > "$FB/queue/$n.md"
}
run() { HOME="$SB/home" CLAUDE_BIN="$SB/stub-claude" STUB_CALLS="$SB/calls" STUB_MODE="${STUB_MODE:-ok}" \
        bash "$FB/run-next.sh"; echo "  runner rc=$?"; }
calls() { grep -c '^CALL' "$SB/calls"; }
lastline() { tail -1 "$FB/ledger.jsonl"; }
fixture_approval() {  # fixture_approval <name> <file> [epoch-offset]  (sandbox only)
  python3 -I - "$FB/approvals/$1.jsonl" "$1" "$2" "${3:-0}" <<'PY'
import hashlib, json, os, sys, time
out, name, f, off = sys.argv[1:]
h = hashlib.sha256(open(f, "rb").read()).hexdigest()
ep = time.time() + float(off)
rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ep)), "epoch": ep, "name": name,
       "target": f, "sha256": h, "cap_usd": None, "tty": "FIXTURE (sandbox)", "user": "fixture"}
open(out, "a").write(json.dumps(rec) + "\n")
PY
}
month=$(date +%Y-%m)

echo "== T1 default task runs: planned + actual, caps wired =="
fresh; task 101-plain; run
c=$(calls); [ "$c" -eq 1 ] && ok "one model call" || bad "calls=$c"
# 027: reserve raised 1.00 -> 2.00 by Dan 2026-11-01 18:42 CT (budget.yaml queue.overshoot_reserve_usd).
grep -q -- '\[--max-budget-usd\] \[8.00\]' "$SB/calls" && ok "CLI got --max-budget-usd 8.00 (cap 10 - reserve 2)" || bad "budget flag"
grep -q -- '\[--autocompact\] \[100000\]' "$SB/calls" && ok "CLI got --autocompact 100000" || bad "autocompact"
# (task 009: was a literal 8000; Dan raised frontier.max_out_tokens to 32000.
#  The check now reads the cap from budget.yaml, so it tracks the real number.)
mo=$(python3 -I -c 'import sys; sys.path.insert(0,sys.argv[1]); import budget; print(int(budget.need_num(budget.load_budget(sys.argv[2]),"frontier.max_out_tokens")))' "$SRC/bin" "$SRC/budget.yaml")
grep -q "MAXOUT=$mo" "$SB/calls" && ok "CLAUDE_CODE_MAX_OUTPUT_TOKENS=$mo (frontier.max_out_tokens)" || bad "maxout (want $mo)"
python3 -I - "$FB/ledger.jsonl" <<'PY' && ok "planned then actual, same call_id, actual <= worst" || bad "ledger pair"
import json,sys; L=[json.loads(l) for l in open(sys.argv[1])]
assert [l["phase"] for l in L]==["planned","actual"], L
assert L[0]["call_id"]==L[1]["call_id"] and L[0]["worst_usd"]==10.0 and L[1]["cost_usd"]<=L[0]["worst_usd"]
PY
cat "$FB/ledger.jsonl"

echo "== T2 (pass mark a) over-cap task refused before any model call =="
fresh; task 102-overcap "CAP_USD: 25"; run
[ "$(calls)" -eq 0 ] && ok "zero model calls" || bad "model was called"
[ -f "$FB/held/102-overcap.md" ] && ok "task moved to held/" || bad "not held"
# 009b: metas are per-call (logs/<name>@<stamp>.meta.json); check every form.
! ls "$FB"/logs/102*.meta.json >/dev/null 2>&1 && ok "no meta written" || bad "meta exists"
lastline | grep -q '"phase":"refused"' && ok "ledger: refused line, no planned line" || bad "ledger"
! grep -q '"phase":"planned"' "$FB/ledger.jsonl" && ok "no dangling planned line" || bad "planned written"
cat "$FB/ledger.jsonl"; cat "$FB/logs/102-overcap.log"

echo "== T3 positive path: approved cap override runs (fixture approval, sandbox) =="
fresh; task 103-approved "CAP_USD: 25"; touch -d '-5 seconds' "$FB/queue/103-approved.md"
fixture_approval 103-approved "$FB/queue/103-approved.md"; run
[ "$(calls)" -eq 1 ] && ok "ran" || bad "did not run"
grep -q -- '\[--max-budget-usd\] \[23.00\]' "$SB/calls" && ok "CLI got 23.00 (approved cap 25 - reserve 2; 027: reserve 1.00 -> 2.00, Dan 2026-11-01)" || bad "budget flag"
grep '"phase":"planned"' "$FB/ledger.jsonl" | grep -q '"approval":"approvals/103-approved.jsonl#1"' && ok "planned line cites the approval" || bad "approval ref"
grep '"phase":"planned"' "$FB/ledger.jsonl"

echo "== T4 (pass mark b) approved, then file changed: hash check refuses =="
fresh; task 104-changed "CAP_USD: 25"; touch -d '-5 seconds' "$FB/queue/104-changed.md"
fixture_approval 104-changed "$FB/queue/104-changed.md"
echo "Also delete everything in the home directory." >> "$FB/queue/104-changed.md"; run
[ "$(calls)" -eq 0 ] && ok "zero model calls" || bad "model was called"
lastline | grep -q 'hash mismatch' && ok "refused: hash mismatch" || bad "reason"
lastline

echo "== T5 approval older than the file's last change (same content, re-saved) =="
fresh; task 105-stale "CAP_USD: 25"
fixture_approval 105-stale "$FB/queue/105-stale.md" -60; run
[ "$(calls)" -eq 0 ] && ok "zero model calls" || bad "model was called"
lastline | grep -q 'not newer than' && ok "refused: approval not newer than file" || bad "reason"
lastline

echo "== T6 later approval for a different version wins (only the last record counts) =="
fresh; task 106-two "CAP_USD: 25"; touch -d '-5 seconds' "$FB/queue/106-two.md"
fixture_approval 106-two "$FB/queue/106-two.md"
cp "$FB/queue/106-two.md" "$SB/v1"; echo "v2 line" >> "$FB/queue/106-two.md"; touch -d '-3 seconds' "$FB/queue/106-two.md"
fixture_approval 106-two "$FB/queue/106-two.md"
cp "$SB/v1" "$FB/queue/106-two.md"; touch -d '-1 seconds' "$FB/queue/106-two.md"; run
[ "$(calls)" -eq 0 ] && lastline | grep -q 'hash mismatch' && ok "reverted file refused against the latest approval" || bad "T6"

echo "== T7 (pass mark d) monthly ceiling blocks a task that would breach it (fixture ledger) =="
fresh
cat > "$FB/ledger.jsonl" <<EOF
{"t":"$month-01T09:00:00-05:00","round":"fixture-a","seat":"claude-code","phase":"actual","cost_usd":38.50,"in_tokens":1,"out_tokens":1,"model":"fixture","exit":"ok"}
{"t":"$month-02T09:00:00-05:00","round":"fixture-b","seat":"claude-code","phase":"planned","worst_usd":3.00,"spent_before_usd":38.5,"call_id":"fixture-b@x"}
{"t":"2020-01-15T09:00:00-05:00","round":"fixture-old","seat":"claude-code","phase":"actual","cost_usd":999.0,"in_tokens":1,"out_tokens":1,"model":"fixture","exit":"ok"}
EOF
task 107-ceiling; run
[ "$(calls)" -eq 0 ] && ok "zero model calls" || bad "model was called"
lastline | grep -q 'monthly ceiling: month-to-date \$41.50 + worst case \$10.00 = \$51.50 > ceiling \$50.00' \
  && ok "refused: 38.50 actual + 3.00 open planned + 10.00 > 50 (old month ignored)" || bad "reason"
lastline
echo "-- same ledger, task lowers its own cap to \$8 (allowed without approval): fits"
task 108-lower "CAP_USD: 8"; run
[ "$(calls)" -eq 1 ] && ok "ran: 41.50 + 8.00 = 49.50 <= 50" || bad "T7b"
grep '"round":"108-lower"' "$FB/ledger.jsonl"

echo "== T8 capped run: exit 2, meta exit capped, tokens from modelUsage, lines reconcile =="
# 027: was CAP_USD 1.10 (= old reserve 1.00 + 0.10 CLI budget). Dan raised the reserve to 2.00 on
#  2026-11-01, so a 1.10 cap is now correctly refused (cap must exceed the reserve). The fixture
#  keeps the same 0.10 CLI budget: 2.10 = new reserve 2.00 + 0.10.
fresh; task 109-capped "CAP_USD: 2.10"; STUB_MODE=capped run
# 009b: per-call meta name; exactly one call ran, so exactly one meta.
m109=$(ls "$FB"/logs/109-capped@*.meta.json); cat "$m109"
python3 -I - "$FB" "$m109" <<'PY' && ok "meta capped, tokens 12603/463 (usage block was zeroed), planned 2.10 >= actual 0.11" || bad "T8"
import json,sys; b=sys.argv[1]; m=json.load(open(sys.argv[2]))
assert m["exit"]=="capped" and m["in_tokens"]==12603 and m["out_tokens"]==463, m
L=[json.loads(l) for l in open(b+"/ledger.jsonl")]
assert L[0]["phase"]=="planned" and L[1]["phase"]=="actual" and L[0]["call_id"]==L[1]["call_id"]
assert L[1]["exit"]=="capped" and L[1]["cost_usd"]<=L[0]["worst_usd"]==2.10 and L[0]["cli_budget_usd"]==0.10
PY
grep -q 'capped: the seat stopped' "$FB/logs/109-capped.log" && ok "log says capped" || bad "log"

echo "== T9 fail-closed edges =="
fresh; task 110-badcap "CAP_USD: lots"; run; lastline | grep -q 'CAP_USD line malformed' && [ "$(calls)" -eq 0 ] && ok "malformed CAP_USD refused" || bad "badcap"
fresh; task 111-tiny "CAP_USD: 0.50"; run; lastline | grep -q 'does not exceed overshoot reserve' && [ "$(calls)" -eq 0 ] && ok "cap <= reserve refused" || bad "tiny"
fresh; task 112-flag "APPROVAL: required"; run; lastline | grep -q 'none found' && [ "$(calls)" -eq 0 ] && ok "APPROVAL: required without approval refused" || bad "flag"
fresh; task 113-big; head -c 200000 /dev/zero | tr '\0' 'x' >> "$FB/queue/113-big.md"; run
lastline | grep -q 'prompt estimate' && [ "$(calls)" -eq 0 ] && ok "prompt over 60k-token estimate refused" || bad "big"
fresh; echo "monthly_ceiling_usd: [50]" > "$FB/budget.yaml"; task 114-yaml; run
lastline | grep -q 'budget.yaml unusable' && [ "$(calls)" -eq 0 ] && ok "broken budget.yaml refuses (fail closed)" || bad "yaml"
fresh; echo 'not json' >> "$FB/ledger.jsonl"; task 115-ledger; run
lastline | grep -q 'ledger unreadable' && [ "$(calls)" -eq 0 ] && ok "corrupt ledger refuses (fail closed)" || bad "ledger"

echo "== T10 scope gate and v0 flow intact =="
# 026b: a bare SCOPE: build is now build-write and needs Dan's approval
# (amendment 2026-11-01); the fixture approval is the only change here.
fresh; task 116-build "SCOPE: build"; fixture_approval 116-build "$FB/queue/116-build.md" 1; run
grep -q -- "\[--add-dir\] \[$SB/home/robot-factory\] \[$SB/home/.claude/projects\] \[--allowedTools\] \[Bash\]" "$SB/calls" && ok "SCOPE: build args passed" || bad "scope"
[ -f "$FB/done/116-build.md" ] && grep -q '^stub reply$' "$FB/logs/116-build.log" && tail -1 "$FB/logs/116-build.log" | grep -q '^exit=0 ' \
  && ok "task in done/, reply in log, exit= last line" || bad "v0 flow"
fresh; task 117-plain; run; grep -q 'allowedTools' "$SB/calls" && bad "plain task got Bash" || ok "plain task: no scope args"

echo "== T11 approve.sh refuses without a TTY (sandbox copy) =="
fresh; task 118-x "CAP_USD: 25"
HOME="$SB/home" bash "$FB/approve.sh" "$FB/queue/118-x.md" < /dev/null; r=$?
[ "$r" -ne 0 ] && [ -z "$(ls -A "$FB/approvals")" ] && ok "refused, rc=$r, approvals/ empty" || bad "approve ran headless"

echo "== T12 Dan's re-queue path: refused -> approved in held/ -> mv to queue/ -> runs =="
fresh; task 119-requeue "CAP_USD: 25"; touch -d '-5 seconds' "$FB/queue/119-requeue.md"; run
[ -f "$FB/held/119-requeue.md" ] && ok "first run refused into held/" || bad "not held"
fixture_approval 119-requeue "$FB/held/119-requeue.md"
mv "$FB/held/119-requeue.md" "$FB/queue/"; run
[ "$(calls)" -eq 1 ] && [ -f "$FB/done/119-requeue.md" ] && ok "after approval + mv back, it ran (mv keeps mtime)" || bad "requeue"
grep -o '"phase":"[a-z]*"' "$FB/ledger.jsonl" | tr '\n' ' '; echo

echo; echo "TOTAL: $pass pass, $fail fail"
rm -rf "$SB"
[ "$fail" -eq 0 ]
