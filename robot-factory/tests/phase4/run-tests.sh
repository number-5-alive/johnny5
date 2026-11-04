#!/usr/bin/env bash
# Phase 4 sandbox tests (task 011): sessions (bin/session.py) and the scribe's
# --session mode. Phase 2/3 style: throwaway fake HOME under
# tests/phase4/sandbox/, the factory's files copied in, real budget.py and real
# adapters run against two stubs: a stub claude (CLAUDE_BIN) that reads its
# prompt on stdin and answers from a scripted queue, and a stub Ollama
# (OLLAMA_URL, port-only hook) that does the same. The real Ollama, the live
# laya-qwen service and the real ledger are not touched.
# Usage: run-tests.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HOME/robot-factory"
SB="$HERE/sandbox"; FB="$SB/home/robot-factory"
pass=0; fail=0
ok()  { echo "  PASS: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }

# Each stub pops the lowest-numbered file from its queue dir; empty queue ->
# a default reply (the scribe's note comes from that default).
cat > "$HERE/.stub-ollama.py" <<'PY'
import http.server, json, os, sys
sb = sys.argv[1]
def pop(q, default):
    d = os.path.join(sb, q); fs = sorted(os.listdir(d), key=lambda x: int(x))
    if not fs: return default
    p = os.path.join(d, fs[0]); t = open(p).read(); os.remove(p); return t
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with open(os.path.join(sb, "reqs"), "a") as f: f.write(body.decode() + "\n")
        r = {"model": "qwen3.6:27b", "message": {"role": "assistant", "content": pop("qq", "The session ran and closed by rule.")},
             "done": True, "done_reason": "stop", "prompt_eval_count": 120, "eval_count": 30,
             "total_duration": 500000000, "load_duration": 1000000,
             "prompt_eval_duration": 100000000, "eval_duration": 300000000}
        out = json.dumps(r).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(os.path.join(sb, "port"), "w").write(str(s.server_address[1]))
s.serve_forever()
PY

stub_claude() {
cat > "$SB/stub-claude" <<'EOF'
#!/usr/bin/env python3
import json, os, sys
sb = os.environ["STUB_SB"]
stdin = sys.stdin.read()
with open(os.path.join(sb, "calls"), "a") as f:
    f.write("CALL cwd=%s files=%d stdin=%d %s\n" % (os.getcwd(), len(os.listdir(".")), len(stdin), json.dumps(sys.argv[1:])))
d = os.path.join(sb, "cq"); fs = sorted(os.listdir(d), key=lambda x: int(x))
t = "stub reply"
if fs:
    p = os.path.join(d, fs[0]); t = open(p).read(); os.remove(p)
err = t.startswith("@ERROR")
print(json.dumps({"type": "result", "subtype": "error_during_execution" if err else "success", "is_error": err,
  "result": t, "total_cost_usd": 0.25,
  "usage": {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 50},
  "modelUsage": {"claude-opus-5-5": {"inputTokens": 5, "cacheCreationInputTokens": 0, "cacheReadInputTokens": 0, "outputTokens": 50, "costUSD": 0.25}}}))
EOF
chmod +x "$SB/stub-claude"
}

PORT=; SPID=; NC=0; NQ=0
fresh() {
  [ -n "$SPID" ] && kill "$SPID" 2>/dev/null
  rm -rf "$SB"; mkdir -p "$FB"/{seats,bin,rulesets,sessions,records} "$SB/cq" "$SB/qq"
  cp "$SRC/seats/claude_code.sh" "$SRC/seats/qwen_local.sh" "$FB/seats/"
  cp "$SRC/bin/budget.py" "$SRC/bin/scribe.py" "$SRC/bin/session.py" "$FB/bin/"
  cp "$SRC/rulesets/"*.json "$FB/rulesets/"; cp "$SRC/budget.yaml" "$FB/"
  chmod +x "$FB/seats/"*.sh
  : > "$FB/ledger.jsonl"; : > "$SB/calls"; : > "$SB/reqs"; NC=0; NQ=0; stub_claude
  python3 -I "$HERE/.stub-ollama.py" "$SB" & SPID=$!
  for _ in $(seq 50); do [ -s "$SB/port" ] && break; sleep 0.1; done
  PORT=$(cat "$SB/port")
}
trap '[ -n "$SPID" ] && kill "$SPID" 2>/dev/null; rm -f "$HERE/.stub-ollama.py"' EXIT
cq() { NC=$((NC+1)); printf '%s' "$1" > "$SB/cq/$NC"; }      # queue a claude reply
qq() { NQ=$((NQ+1)); printf '%s' "$1" > "$SB/qq/$NQ"; }      # queue a qwen reply
brief() { local sid=$1; shift; mkdir -p "$FB/sessions/$sid"
  { for l in "$@"; do echo "$l"; done; echo; echo "Write a short test page about stubs."; } > "$FB/sessions/$sid/brief.md"; }
FSEATS=("RULESET: factory" "SEAT drafter: claude_code" "SEAT critic: qwen_local" "SEAT merger: claude_code")
srun() { HOME="$SB/home" CLAUDE_BIN="$SB/stub-claude" STUB_SB="$SB" OLLAMA_URL="http://127.0.0.1:$PORT" \
         python3 -I "$FB/bin/session.py" run "$1" > "$SB/out" 2>&1; rc=$?; }
S() { echo "$FB/sessions/$1"; }
sj() { python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); print(eval(sys.argv[2],{"m":m}))' "$(S "$1")/session.json" "$2"; }
lj() { python3 -I -c 'import json,sys; L=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]; print(eval(sys.argv[2],{"L":L}))' "$FB/ledger.jsonl" "$1"; }
ncall() { grep -c '^CALL' "$SB/calls"; }
V1=$'DRAFT\n\nStubs answer when the real seats should not.'
V2=$'DRAFT\n\nStubs answer when the real seats should not. They keep tests cheap.'
MERGE2=$'=== MERGE RECORD ===\nP1: ACCEPT - fair, added the cost line.\nP2: REJECT - the brief asks for short, so no history.\n=== ARTIFACT ===\n'"$V2"

echo "== B1 (P1) a full cycle: compose, critique, merge, critique -> converged =="
fresh; brief 901-conv "${FSEATS[@]}" "MAX_ROUNDS: 2" "FORBID: em-dash" "LABEL: DRAFT"
cq "$V1"; qq $'P1: Say why stubs are cheap.\nP2: Add some history.'; cq "$MERGE2"; qq "NO SUBSTANTIVE POINTS"
srun 901-conv; D=$(S 901-conv)
[ "$rc" -eq 0 ] && ok "rc 0" || bad "rc=$rc $(cat "$SB/out")"
[ "$(sj 901-conv '(m["status"],m["versions"])')" = "('converged', ['r0-drafter-v1.md', 'r1-merger-v2.md'])" ] && ok "converged; v1 and v2 are separate files" || bad "$(sj 901-conv '(m["status"],m["stop_reason"],m["versions"])')"
[ "$(cat "$D/r0-drafter-v1.md")" = "$V1" ] && [ "$(cat "$D/r1-merger-v2.md")" = "$V2" ] && ok "v1 preserved verbatim alongside v2" || bad "version text"
grep -q '^P1: Say why stubs are cheap.$' "$D/r1-critic-critique.md" && grep -q '^NO SUBSTANTIVE POINTS$' "$D/r2-critic-critique.md" && ok "both critiques on file" || bad "critique files"
R="$D/r1-merger-record.md"
grep -q '| P1 | Say why stubs are cheap. | ACCEPT | fair, added the cost line. |' "$R" && grep -q '| P2 | Add some history. | REJECT |' "$R" && ok "merge record answers every point with a reason" || bad "record $(cat "$R")"
grep -q -A3 '^## Disagreements' "$R" && grep -q 'Rejected because: the brief asks for short' "$R" && ok "rejected point surfaced under Disagreements" || bad "disagreements"
[ "$(sj 901-conv '(m["rounds"][0]["accepted"],m["rounds"][0]["rejected"],len(m["rounds"]))')" = "(['P1'], ['P2'], 2)" ] && ok "session.json carries accept/reject per round" || bad "rounds json"
[ "$(sj 901-conv 'm["final_checks"]')" = "{'words': 13, 'label_first_line': True, 'forbidden_counts': {'em-dash': 0}}" ] && ok "final checks: DRAFT first line, no em dash" || bad "$(sj 901-conv 'm["final_checks"]')"
[ "$(lj 'len(L)')" = 8 ] && [ "$(lj 'sorted(set(l["round"] for l in L))')" = "['901-conv']" ] && ok "4 calls -> 8 ledger lines (planned+actual each), all round == session id" || bad "ledger $(lj 'len(L)')"
[ "$(lj '[(l["phase"],l.get("seat")) for l in L if l["phase"]=="actual"]')" = "[('actual', 'claude-code'), ('actual', 'qwen-local'), ('actual', 'claude-code'), ('actual', 'qwen-local')]" ] && ok "actual lines in call order, by seat" || bad "$(lj '[(l["phase"],l.get("seat")) for l in L]')"
[ "$(lj 'round(sum(l.get("cost_usd") or 0 for l in L if l["phase"]=="actual"),2)')" = 0.5 ] && ok "session actual \$0.50 = 2 stub claude calls; qwen \$0" || bad "cost sum"
grep -q '^CAP_USD: 3.33$' "$D/calls/01-drafter-compose.task.md" && ok "per-call cap \$3.33 = floor(\$10.00 / 3 frontier calls)" || bad "cap line"
grep -q '^SEAT: qwen_local$' "$D/calls/02-critic-critique.task.md" && ok "critic call preflighted as qwen_local" || bad "seat line"
[ "$(ncall)" = 2 ] && ok "2 claude calls" || bad "ncall $(ncall)"
grep -q '"--tools", ""' "$SB/calls" && ! grep -q 'permission-mode' "$SB/calls" && # 027: per-call cap 3.33 (10.00 / 3) minus reserve. Reserve raised 1.00 -> 2.00 by Dan 2026-11-01, so 2.33 -> 1.33.
grep -q '"--max-budget-usd", "1.33"' "$SB/calls" && ok "claude seat word-only: --tools \"\", no permission mode, cli budget cap-reserve 1.33" || bad "args $(head -1 "$SB/calls")"
grep -q 'files=0' "$SB/calls" && ! grep -q 'stdin=0 ' "$SB/calls" && ok "claude ran in an empty scratch dir with the prompt on stdin" || bad "cwd/stdin"
grep -q 'Stubs answer when' "$(sed -n 2p "$SB/reqs" > "$SB/r2"; echo "$SB/r2")" && ok "critic was sent the current version" || bad "critic prompt"
for f in "$FB/records/901-conv-record.md"; do
  [ -f "$f" ] && grep -q 'PENDING MODERATOR REVIEW' "$f" && grep -q '### Rounds (from `sessions/901-conv/session.json`)' "$f" && ok "scribe record written, rounds summarized, PENDING MODERATOR REVIEW" || bad "record missing $(tail -3 "$D/session.log")"; done
grep -q 'sessions/901-conv/r1-merger-record.md' "$FB/records/901-conv-record.md" && ok "record lists the session files with hashes" || bad "deliverables list"
grep -q 'scribe exit 0' "$D/session.log" && ok "session.log records the scribe's exit" || bad "scribe exit"

echo "== B2 sessions run once; files never overwritten =="
cp "$D/r0-drafter-v1.md" "$SB/v1.before"; srun 901-conv
[ "$rc" -eq 2 ] && grep -q 'already run' "$SB/out" && ok "re-run refused (rc 2)" || bad "rerun rc=$rc"
cmp -s "$SB/v1.before" "$D/r0-drafter-v1.md" && [ "$(lj 'len(L)')" = 8 ] && ok "nothing changed, no ledger lines" || bad "changed"

echo "== B3 round cap read from budget.yaml; MAX_ROUNDS may only lower it =="
fresh; brief 902-cap "${FSEATS[@]}" "MAX_ROUNDS: 1" "LABEL: DRAFT"
cq "$V1"; qq $'P1: Say why stubs are cheap.\nP2: Add some history.'; cq "$MERGE2"
srun 902-cap
[ "$rc" -eq 0 ] && [ "$(sj 902-cap '(m["status"],len(m["versions"]),m["per_call_cap_usd"])')" = "('round_cap', 2, 5.0)" ] && ok "stops at round cap 1, status round_cap, per-call cap \$5.00 (2 frontier calls)" || bad "rc=$rc $(cat "$SB/out")"
brief 903-over "${FSEATS[@]}" "MAX_ROUNDS: 4"; srun 903-over
[ "$rc" -eq 2 ] && grep -q 'may only lower' "$SB/out" && [ ! -e "$(S 903-over)/calls" ] && ok "MAX_ROUNDS 4 > factory.round_cap 3 refused, no calls" || bad "rc=$rc"
sed -i 's/^  round_cap: 3/  round_cap: 1/' "$FB/budget.yaml"
brief 904-yaml "${FSEATS[@]}"; cq "$V1"; qq "P1: x"; cq $'=== MERGE RECORD ===\nP1: ACCEPT - ok\n=== ARTIFACT ===\nDRAFT\n\ny'
srun 904-yaml
[ "$(sj 904-yaml '(m["rounds_allowed"],m["status"])')" = "(1, 'round_cap')" ] && ok "round_cap edited in budget.yaml is what the session uses" || bad "$(cat "$SB/out")"

echo "== B4 meld rule: an unanswered point halts, no new version =="
fresh; brief 905-meld "${FSEATS[@]}" "LABEL: DRAFT"
cq "$V1"; qq $'P1: one\nP2: two'; cq $'=== MERGE RECORD ===\nP1: ACCEPT - yes\n=== ARTIFACT ===\nDRAFT\n\nblended'
srun 905-meld
[ "$rc" -eq 6 ] && [ "$(sj 905-meld '(m["status"],m["versions"])')" = "('halted', ['r0-drafter-v1.md'])" ] && grep -q 'not answered: P2' "$(S 905-meld)/session.log" && ok "halted rc 6, P2 unanswered named, no v2" || bad "rc=$rc $(sj 905-meld 'm["stop_reason"]')"
[ "$(lj 'len([l for l in L if l["phase"]=="actual"])')" = 3 ] && ok "the merge call still has its actual line" || bad "actuals"
[ -f "$FB/records/905-meld-record.md" ] && ok "halted session still recorded" || bad "no record"
fresh; brief 906-extra "${FSEATS[@]}"; cq "$V1"; qq 'P1: one'; cq $'=== MERGE RECORD ===\nP1: ACCEPT - y\nP2: REJECT - n\n=== ARTIFACT ===\nx'
srun 906-extra; [ "$rc" -eq 6 ] && grep -q 'not raised: P2' "$(S 906-extra)/session.log" && ok "answer for a point never raised: halted" || bad "extra rc=$rc"
fresh; brief 907-shape "${FSEATS[@]}"; cq "$V1"; qq 'P1: one'; cq 'I agree with everything. DRAFT new text.'
srun 907-shape; [ "$rc" -eq 6 ] && grep -q 'lacks' "$(S 907-shape)/session.log" && ok "merge without a record section: halted" || bad "shape rc=$rc"
fresh; brief 908-twice "${FSEATS[@]}"; cq "$V1"; qq 'P1: one'; cq $'=== MERGE RECORD ===\nP1: ACCEPT - y\nP1: REJECT - n\n=== ARTIFACT ===\nx'
srun 908-twice; [ "$rc" -eq 6 ] && grep -q 'more than once' "$(S 908-twice)/session.log" && ok "point answered twice: halted" || bad "twice rc=$rc"

echo "== B5 critique that does not parse halts =="
fresh; brief 909-crit "${FSEATS[@]}"; cq "$V1"; qq 'Looks great overall, a few thoughts.'
srun 909-crit; [ "$rc" -eq 6 ] && grep -q 'did not parse' "$(S 909-crit)/session.log" && [ "$(ncall)" = 1 ] && ok "halted, no merge call made" || bad "rc=$rc"
fresh; brief 910-lenient "${FSEATS[@]}" "MAX_ROUNDS: 1"; cq "$V1"; qq $'<think>hmm</think>\n- **P1:** first\n  continued\n2) nope\n* P2) second'
cq $'=== MERGE RECORD ===\n- **P1**: **ACCEPT** - a\nP2: REJECT: b\n=== ARTIFACT ===\nDRAFT\n\nz'
srun 910-lenient; grep -q '^P1: first continued 2) nope$' "$(S 910-lenient)/r1-critic-critique.md" && [ "$rc" -eq 0 ] && ok "markdown-decorated points and records parse; think block stripped" || bad "rc=$rc $(cat "$(S 910-lenient)/r1-critic-critique.md")"

echo "== B6 mechanical checks are points too (critic says none, artifact breaks a rule) =="
fresh; brief 911-mech "${FSEATS[@]}" "MAX_ROUNDS: 2" "FORBID: em-dash" "LABEL: DRAFT"
cq $'Stubs — cheap.'; qq "NO SUBSTANTIVE POINTS"
cq $'=== MERGE RECORD ===\nM1: ACCEPT - removed it\nM2: ACCEPT - added label\n=== ARTIFACT ===\nDRAFT\n\nStubs are cheap.'; qq "NO SUBSTANTIVE POINTS"
srun 911-mech
grep -q '^M1: The artifact contains the em dash' "$(S 911-mech)/r1-critic-critique.md" && grep -q "^M2: The artifact's first line" "$(S 911-mech)/r1-critic-critique.md" && ok "em dash and missing label raised as M1, M2" || bad "$(cat "$(S 911-mech)/r1-critic-critique.md")"
[ "$(sj 911-mech '(m["status"],len(m["versions"]),m["final_checks"]["forbidden_counts"])')" = "('converged', 2, {'em-dash': 0})" ] && ok "merged, then converged clean" || bad "$(sj 911-mech 'm')"
grep -q 'em dash (U+2014)' "$(S 911-mech)/calls/01-drafter-compose.prompt.md" && ok "forbid rule is in the drafter's prompt" || bad "forbid prompt"

echo "== B7 brief refusals: SCOPE, per-call terms, unknown header, missing role =="
fresh
for bad_line in "SCOPE: build" "CAP_USD: 9.00" "APPROVAL: x" "SEAT: qwen_local" "PRIORITY: high"; do
  brief 912-ref "${FSEATS[@]}" "$bad_line"; srun 912-ref
  [ "$rc" -eq 2 ] && [ ! -e "$(S 912-ref)/calls" ] && ok "'$bad_line' refused, no calls" || bad "$bad_line rc=$rc"; done
brief 913-role "RULESET: factory" "SEAT drafter: claude_code" "SEAT critic: qwen_local"; srun 913-role
[ "$rc" -eq 2 ] && grep -q "role 'merger'" "$SB/out" && ok "unseated role refused" || bad "role rc=$rc"
brief 914-seat "${FSEATS[@]}" "SEAT judge: claude_code"; srun 914-seat
[ "$rc" -eq 2 ] && ok "role the ruleset lacks refused" || bad "judge rc=$rc"
mkdir -p "$(S BAD)"; srun BAD; [ "$rc" -eq 2 ] && ok "bad session id refused" || bad "sid"
[ "$(lj 'len(L)')" = 0 ] && [ "$(ncall)" = 0 ] && ok "refusals made no calls and no ledger lines" || bad "leak"

echo "== B8 money: session cap from the ledger, preflight refusal, adapter failure =="
fresh; brief 915-spent "${FSEATS[@]}"
echo '{"t": "'"$(date +%Y-%m)"'-01T00:00:00+00:00", "round": "915-spent", "phase": "planned", "call_id": "915-x", "worst_usd": 8.00}' > "$FB/ledger.jsonl"
srun 915-spent
[ "$rc" -eq 6 ] && grep -q 'session cap: session so far \$8.00 + this call.s cap \$2.50' "$(S 915-spent)/session.log" && [ "$(ncall)" = 0 ] && ok "open \$8.00 for this session + per-call \$2.50 (4 frontier calls at round_cap 3) > \$10: halted before any call" || bad "rc=$rc $(sj 915-spent 'm["stop_reason"]')"
fresh; brief 916-month "${FSEATS[@]}"
echo '{"t": "'"$(date +%Y-%m)"'-01T00:00:00+00:00", "round": "other", "phase": "actual", "call_id": "o-1", "cost_usd": 48.00}' > "$FB/ledger.jsonl"
srun 916-month
[ "$rc" -eq 6 ] && grep -q 'preflight refused call 01' "$(S 916-month)/session.log" && [ "$(ncall)" = 0 ] && ok "monthly ceiling: preflight REFUSED, session halted, no call" || bad "rc=$rc $(tail -3 "$(S 916-month)/session.log")"
fresh; brief 917-err "${FSEATS[@]}"; cq "@ERROR"
srun 917-err
[ "$rc" -eq 6 ] && grep -q 'seat claude-code exited' "$(S 917-err)/session.log" && [ "$(lj 'len([l for l in L if l["phase"]=="actual"])')" = 1 ] && ok "adapter error: actual line written, then halted" || bad "rc=$rc $(tail -3 "$(S 917-err)/session.log")"
fresh; brief 918-badledger "${FSEATS[@]}"; echo 'not json' > "$FB/ledger.jsonl"; srun 918-badledger
[ "$rc" -eq 6 ] && grep -q 'ledger unreadable' "$(S 918-badledger)/session.log" && [ "$(ncall)" = 0 ] && ok "corrupt ledger: halted, fail closed" || bad "rc=$rc"

echo "== B9 pause on a big artifact (artifact_pause_tokens from budget.yaml) =="
fresh; brief 919-big "${FSEATS[@]}"; cq "DRAFT $(head -c 61000 /dev/zero | tr '\0' 'a')"
srun 919-big
[ "$rc" -eq 5 ] && [ "$(sj 919-big '(m["status"],len(m["versions"]))')" = "('paused', 1)" ] && grep -q 'PAUSE: artifact v1 estimated 20336 tokens > artifact_pause_tokens 20000' "$(S 919-big)/session.log" && ok "61006 chars / 3 = 20336 tokens > 20000: paused rc 5 before the critic" || bad "rc=$rc $(grep PAUSE "$(S 919-big)/session.log")"

echo "== B10 SAINT sketch runs on the same machine (data only) =="
fresh; brief 920-saint "RULESET: saint" "SEAT proposer: claude_code" "SEAT challenger: qwen_local" "SEAT chair: claude_code" "MAX_ROUNDS: 1"
cq "Position: stubs are fine."; qq "P1: Stubs can drift from the real seat."; cq $'=== MERGE RECORD ===\nP1: ACCEPT - true\n=== ARTIFACT ===\nPosition: stubs are fine if checked live.'
srun 920-saint
[ "$rc" -eq 0 ] && [ "$(sj 920-saint '(m["ruleset"],m["budget_section"],m["session_cap_usd"],m["versions"])')" = "('saint', 'saint', 5.0, ['r0-proposer-v1.md', 'r1-chair-v2.md'])" ] && ok "saint: proposer/challenger/chair, saint.session_cap_usd \$5.00, own version names" || bad "rc=$rc $(cat "$SB/out")"
grep -q 'SAINT deliberation' "$(S 920-saint)/calls/01-proposer-compose.prompt.md" && ok "prompts came from rulesets/saint.json" || bad "saint prompt"

echo "== B11 ruleset validation =="
fresh; python3 -I - "$FB/rulesets" <<'PY'
import json,sys,os
d=sys.argv[1]; r=json.load(open(os.path.join(d,"factory.json")))
r["name"]="threestep"; r["cycle"].append({"step":"critique","role":"critic"}); json.dump(r,open(os.path.join(d,"threestep.json"),"w"))
r["name"]="badstep"; r["cycle"]=[{"step":"vote","role":"critic"}]; json.dump(r,open(os.path.join(d,"badstep.json"),"w"))
PY
for rs in threestep badstep nosuch; do brief 921-rs "RULESET: $rs" "SEAT drafter: claude_code" "SEAT critic: qwen_local" "SEAT merger: claude_code"; srun 921-rs
  [ "$rc" -eq 2 ] && ok "ruleset $rs refused" || bad "$rs rc=$rc"; done

echo
echo "phase4: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
