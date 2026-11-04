#!/usr/bin/env bash
# Phase 7 sandbox tests (task 015): the SAINT ruleset on the session machine:
# standings turn, decision record, envelope refusals. Phase 4 harness: throwaway fake HOME under
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
# 027 stop rule (task 027 item 3): checks inside a STOPID section whose SAINT room was refused by
# "per-call cap ... does not exceed the overshoot reserve" are reported KNOWN-FAILING-PENDING-RULING,
# not passed and not hidden. Any other failure in those sections is still a plain FAIL.
# Decision for Dan: work/027-suite-rebaseline/REPORT.md, "Stopped decisions", 027-S1.
STOPID=; RESV=0; stopped=0; STOPPED_NAMES=()
bad() { if [ -n "$STOPID" ] && [ "$RESV" = 1 ]; then echo "  KNOWN-FAILING-PENDING-RULING [$STOPID]: $*"; stopped=$((stopped+1)); STOPPED_NAMES+=("[$STOPID] $SECNAME: $*")
        else echo "  FAIL: $*"; fail=$((fail+1)); fi; }
stopsec() { STOPID=$1; SECNAME=$2; RESV=0; }; endstop() { STOPID=; RESV=0; }

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
  # 027 evidence mode only (never the default): RF027_SHADOW_RESERVE=1.00 runs the suite with the
  # pre-2026-11-01 reserve in the sandbox copy, to show the stopped checks are otherwise green.
  [ -n "${RF027_SHADOW_RESERVE:-}" ] && sed -i "s/^\(  overshoot_reserve_usd:\).*/\1 $RF027_SHADOW_RESERVE/" "$FB/budget.yaml"
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
         python3 -I "$FB/bin/session.py" run "$1" > "$SB/out" 2>&1; rc=$?
         grep -q 'does not exceed the overshoot reserve' "$SB/out" && RESV=1 || true; }
S() { echo "$FB/sessions/$1"; }
sj() { python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); print(eval(sys.argv[2],{"m":m}))' "$(S "$1")/session.json" "$2"; }
lj() { python3 -I -c 'import json,sys; L=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]; print(eval(sys.argv[2],{"L":L}))' "$FB/ledger.jsonl" "$1"; }
ncall() { grep -c '^CALL' "$SB/calls"; }
SB_ID=0
SEATS2=("RULESET: saint" "SEAT proposer: claude_code" "SEAT challenger: qwen_local" "SEAT chair: claude_code")
SEATS1=("RULESET: saint" "SEAT proposer: claude_code" "SEAT challenger: claude_code" "SEAT chair: claude_code")
SL() { python3 -I -c 'import json,sys; L=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]; print(eval(sys.argv[2],{"L":L}))' "$FB/records/logs/scribe-ledger.jsonl" "$1"; }
heads() { grep '^## ' "$1"; }
OPEN=$'Position: the room should pilot a four-day week before any wage change.'
M1=$'=== MERGE RECORD ===\nP1: ACCEPT - the pilot needs a stated length; six months added.\nP2: REJECT - wages are out of scope for the pilot question.\n=== ARTIFACT ===\nPosition: pilot a four-day week for six months before any wage change.'
M2=$'=== MERGE RECORD ===\nP1: REJECT - the six-month length already answers it.\n=== ARTIFACT ===\nPosition: pilot a four-day week for six months before any wage change; review at the end.'
C1=$'P1: The pilot has no stated length.\nP2: Wage effects are ignored entirely.'
C2=$'P1: I still hold that wage effects must be in the pilot (re-raised).'

echo "== T1 brief parsing: AGENDA and SCRIBE headers; bad values refused =="
fresh
python3 -I - "$FB/bin" <<'PY' > "$SB/t1" 2>&1
import sys; sys.path.insert(0, sys.argv[1]); import session as s
b = s.parse_brief("RULESET: saint\nSEAT proposer: claude_code\nSEAT challenger: qwen_local\nSEAT chair: claude_code\n"
                  "MAX_ROUNDS: 2\nAGENDA: Should the room pilot a four-day week?\nSCRIBE: johnny\n\nBody line.\n")
print("OK", b["ruleset"], sorted(b["seats"].items()), b["max_rounds"], b["agenda"], b["scribe"], repr(b["body"].strip()))
for bad in ["RULESET: saint\nSCRIBE: jev\n\nx", "RULESET: saint\nSCRIBE: johnny\nSCRIBE: johnny\n\nx",
            "RULESET: saint\nAGENDA: \n\nx", "RULESET: saint\nMAX_ROUNDS: 2\nMAX_ROUNDS: 1\n\nx"]:
    try: s.parse_brief(bad); print("ACCEPTED", repr(bad))
    except ValueError as e: print("REFUSED", e)
PY
grep -q "^OK saint \[('chair', 'claude_code'), ('challenger', 'qwen_local'), ('proposer', 'claude_code')\] 2 Should the room pilot a four-day week? johnny 'Body line.'$" "$SB/t1" && ok "SEAT role lines, MAX_ROUNDS, AGENDA, SCRIBE parsed; body kept" || bad "$(cat "$SB/t1")"
[ "$(grep -c '^REFUSED' "$SB/t1")" = 4 ] && ! grep -q '^ACCEPTED' "$SB/t1" && ok "SCRIBE: jev, duplicate SCRIBE, empty AGENDA, duplicate MAX_ROUNDS all refused" || bad "$(cat "$SB/t1")"
brief 930-fac "RULESET: factory" "SEAT drafter: claude_code" "SEAT critic: qwen_local" "SEAT merger: claude_code" "AGENDA: x"; srun 930-fac
[ "$rc" -eq 2 ] && grep -q 'decision-record header' "$SB/out" && ok "AGENDA on the factory ruleset refused (rc 2)" || bad "rc=$rc $(cat "$SB/out")"
brief 930-noag "${SEATS2[@]}" "MAX_ROUNDS: 1"; cq "$OPEN"; qq "NO SUBSTANTIVE POINTS"; srun 930-noag
[ "$(sj 930-noag '(m["agenda"],m["agenda_source"],m["scribe"])')" = "('Write a short test page about stubs.', 'first line of the brief body', None)" ] && ok "no AGENDA line: agenda is the body's first line, labelled so" || bad "$(sj 930-noag 'm.get("agenda")') $(cat "$SB/out")"

echo "== T2-T4 two rounds, standings turn between, decision record =="
stopsec 027-S1 "T2-T4 931-two (saint, claude proposer+chair, 2 rounds = 3 frontier calls)"
fresh; brief 931-two "${SEATS2[@]}" "MAX_ROUNDS: 2" "AGENDA: Should the room pilot a four-day week before any wage change?" "SCRIBE: johnny"
cq "$OPEN"; qq "$C1"; cq "$M1"; qq "Two points were raised; one was accepted and one rejected; none is open."; qq "$C2"; cq "$M2"
srun 931-two; D=$(S 931-two)
# 034: cap 5.0 -> 6.5 and per call 1.66 -> 2.16 (floor(650/3)/100) per Dan's ruling 027-S1
# (saint.session_cap_usd 6.50); drift diagnosed in work/028-phase7-diagnostic/REPORT.md, CLOSE check.
[ "$rc" -eq 0 ] && [ "$(sj 931-two '(m["status"],m["versions"],m["session_cap_usd"],m["per_call_cap_usd"])')" = "('round_cap', ['r0-proposer-v1.md', 'r1-chair-v2.md', 'r2-chair-v3.md'], 6.5, 2.16)" ] && ok "two rounds to round_cap; saint \$6.50 cap, per call \$2.16 (3 frontier calls)" || bad "rc=$rc $(cat "$SB/out") $(tail -5 "$D/session.log")"
# T2 role routing
[ "$(ncall)" = 3 ] && ok "3 claude calls: proposer compose, chair merge x2" || bad "ncall $(ncall)"
# 034: CAP_USD 1.66 -> 2.16 in both task-file greps per Dan's ruling 027-S1 (saint.session_cap_usd 6.50);
# drift diagnosed in work/028-phase7-diagnostic/REPORT.md, ROUTING check. SEAT assertions unchanged.
grep -q '^SEAT: qwen_local$' "$D/calls/02-challenger-critique.task.md" && grep -q '^SEAT: qwen_local$' "$D/calls/04-challenger-critique.task.md" && grep -q '^CAP_USD: 2.16$' "$D/calls/01-proposer-compose.task.md" && grep -q '^CAP_USD: 2.16$' "$D/calls/05-chair-merge.task.md" && ok "challenger routed to qwen_local, proposer and chair to claude_code under CAP_USD" || bad "routing"
grep -q 'You are the proposer seat' "$D/calls/01-proposer-compose.prompt.md" && grep -q 'You are the challenger seat' "$D/calls/02-challenger-critique.prompt.md" && grep -q 'You are the chair seat' "$D/calls/03-chair-merge.prompt.md" && ok "each role got its own saint.json prompt" || bad "prompts"
[ "$(grep -c '"--tools", ""' "$SB/calls")" = 3 ] && ok "every claude call ran with --tools \"\" (word-only envelope)" || bad "$(cat "$SB/calls")"
[ "$(sj 931-two '(m["word_only"],m["standings"],m["decision_record"])')" = "(True, True, True)" ] && ok "session.json carries word_only/standings/decision_record" || bad "flags"
# T3 standings
[ -f "$D/r2-state.json" ] && [ -f "$D/r2-standings.md" ] && [ ! -e "$D/r1-standings.md" ] && ok "standings before round 2 only (none before round 1)" || bad "$(ls "$D")"
cmp -s "$D/r2-standings.md" "$FB/records/931-two-r2-standings.md" && ok "session copy is the scribe's records/ file, byte for byte" || bad "copy"
ST="$D/r2-standings.md"
grep -q 'Standings: record, not opinion' "$ST" && grep -q 'carries no vote' "$ST" && ok "standings labelled record-not-opinion, no vote" || bad "label"
[ "$(heads "$ST" | tr '\n' '|')" = "## Positions per seat|## Points answered vs open|## Disagreements outstanding|## Scribe's reading (restates the tally; no vote)|" ] && ok "standings sections: positions, answered vs open, disagreements outstanding, reading" || bad "$(heads "$ST")"
grep -q '^### qwen_local (challenger; also scribe: Johnny (qwen_local)' "$ST" && grep -q '^### claude_code (proposer, chair)$' "$ST" && ok "positions grouped per seat, capacities labelled" || bad "$(grep '^###' "$ST")"
grep -q 'Raised 2; answered 2 (accepted 1, rejected 1); open 0.' "$ST" && grep -q 'P2: Wage effects are ignored entirely.' "$ST" && grep -q 'Chair rejected: wages are out of scope' "$ST" && ok "tally and the outstanding disagreement (P2) computed from the record" || bad "$(cat "$ST")"
grep -q 'Standings before round 2' "$D/calls/04-challenger-critique.prompt.md" && grep -q 'Standings before round 2' "$D/calls/05-chair-merge.prompt.md" && ok "standings in front of both seats speaking in round 2" || bad "r2 prompts"
grep -q 'No standings yet' "$D/calls/02-challenger-critique.prompt.md" && grep -q 'No standings yet' "$D/calls/03-chair-merge.prompt.md" && ok "round 1 prompts say no standings yet" || bad "r1 prompts"
[ "$(SL '[(l["round"],l["purpose"],l["seat"],l["cost_source"],l["cost_usd"]) for l in L if l["purpose"]=="standings"]')" = "[('931-two', 'standings', 'qwen-local', 'local-free', 0.0)]" ] && ok "standings turn has its own scribe-ledger line, local-free" || bad "$(cat "$FB/records/logs/scribe-ledger.jsonl")"
[ "$(lj 'len(L)')" = 10 ] && [ "$(lj 'sum(1 for l in L if "standings" in json.dumps(l))' 2>/dev/null || echo 0)" = 0 ] && ok "main ledger: 5 seat calls x 2 lines; standings is not a seat call" || bad "ledger $(lj 'len(L)')"
grep -q 'standings before round 2: scribe exit 0' "$D/session.log" && ok "session.log records the standings turn" || bad "log"
# T4 decision record
R="$FB/records/931-two-decision-record.md"
[ -f "$R" ] && ok "decision record written under records/" || bad "no record $(tail -3 "$D/session.log")"
[ "$(heads "$R" | tr '\n' '|')" = "## Header|## Positions by round (verbatim)|## Agreements (accepted by the chair)|## Disagreements (rejected by the chair)|## Dissent (preserved)|## Chair's synthesis|## Standings turns|" ] && ok "all sections present, agreements and disagreements apart" || bad "$(heads "$R")"
[ "$(tail -1 "$R")" = "SAINT decision record: agreement, not verification." ] && ok "closes with the stamp" || bad "last line $(tail -1 "$R")"
sed -n 3p "$R" | grep -q 'agreement reached in a SAINT session, not verification' && sed -n 3p "$R" | grep -q 'no verified stamp and no Grasshopper stamp' && ok "header says agreement, not verification; no stamp" || bad "$(sed -n 1,5p "$R")"
[ "$(grep -io 'verified' "$R" | wc -l)" = "$(grep -o 'no verified stamp' "$R" | wc -l)" ] && ok "'verified' appears only negated" || bad "$(grep -in verified "$R")"
grep -q '^- Agenda: Should the room pilot a four-day week before any wage change? (AGENDA line)$' "$R" && grep -q '^RULESET: saint$' "$R" && ok "header names agenda and commission (brief verbatim)" || bad "header"
grep -q '^| `claude_code` | proposer | votes |$' "$R" && grep -q '^| `qwen_local` | challenger | votes |$' "$R" && grep -q '^| `qwen_local` | scribe: Johnny (qwen_local), bin/scribe.py through seats/qwen_local.sh (local) | no vote |$' "$R" && ok "seats and capacities labelled; scribe row says no vote" || bad "$(grep '^| ' "$R")"
for t in "$OPEN" "P1: The pilot has no stated length." "$C2" "P2: REJECT - wages are out of scope for the pilot question." "P1: REJECT - the six-month length already answers it."; do
  grep -qF -- "$t" "$R" || { bad "not verbatim: $t"; continue; }; done; ok "per-round positions quoted verbatim (opening, challenger, chair)"
grep -q '^#### challenger (`qwen_local`)$' "$R" && [ "$(grep -c '^### Round' "$R")" = 3 ] && ok "rounds 0, 1, 2 each with per-seat headings" || bad "rounds"
sed -n '/^## Dissent/,/^## Chair/p' "$R" | grep -q 'Round 1 P2 (challenger, `qwen_local`): Wage effects are ignored entirely.' && sed -n '/^## Dissent/,/^## Chair/p' "$R" | grep -q 'Round 2 P1 (challenger, `qwen_local`): I still hold that wage effects' && ok "dissent preserved in the challenger's words, both rounds" || bad "dissent"
sed -n '/^## Chair/,/^## Standings/p' "$R" | grep -qF 'review at the end.' && sed -n '/^## Agreements/,/^## Disagreements/p' "$R" | grep -q 'Round 1 P1: The pilot has no stated length.' && ok "chair's synthesis is the final version; agreement listed" || bad "synthesis"
grep -q 'sessions/931-two/r2-standings.md' "$R" && grep -q 'The scribe holds no vote.' "$R" && ok "standings turns listed; scribe holds no vote" || bad "tail"
[ -f "$FB/records/931-two-record.md" ] && ok "the ordinary 7-part session record is still written" || bad "record"
HOME="$SB/home" OLLAMA_URL="http://127.0.0.1:$PORT" python3 -I "$FB/bin/scribe.py" --session 931-two > "$SB/out" 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "scribe will not overwrite records without --force" || bad "rc=$rc"
cp "$R" "$HERE/stub-decision-record.md.out"; cp "$ST" "$HERE/stub-standings.md.out"

endstop
echo "== T5 a brief cannot widen its own envelope =="
fresh
for l in "SCOPE: build" "CAP_USD: 50" "SESSION_CAP_USD: 50" "ROUND_CAP: 9" "BUDGET_SECTION: factory" "TOOLS: all" "MODE: build" "APPROVAL: dan" "SEAT: claude_code"; do
  brief 940-wide "${SEATS2[@]}" "$l"; srun 940-wide
  [ "$rc" -eq 2 ] && grep -q 'REFUSED' "$SB/out" && [ ! -e "$(S 940-wide)/calls" ] && ok "header '$l' refused, no calls" || bad "'$l' rc=$rc $(cat "$SB/out")"
  rm -rf "$(S 940-wide)"; done
mkdir -p "$(S 941-body)"; { printf '%s\n' "${SEATS2[@]}"; echo; echo "Question text."; echo "SESSION_CAP_USD: 50"; } > "$(S 941-body)/brief.md"; srun 941-body
[ "$rc" -eq 2 ] && [ "$(ncall)" = 0 ] && ok "a widening line hidden in the body is refused too" || bad "rc=$rc"

echo "== T6 MAX_ROUNDS may only lower the cap =="
brief 942-raise "${SEATS2[@]}" "MAX_ROUNDS: 4"; srun 942-raise
[ "$rc" -eq 2 ] && grep -q 'may only lower' "$SB/out" && [ ! -e "$(S 942-raise)/calls" ] && ok "MAX_ROUNDS 4 > saint.round_cap 3 refused, no calls" || bad "rc=$rc $(cat "$SB/out")"
brief 943-dup "${SEATS2[@]}" "MAX_ROUNDS: 1" "MAX_ROUNDS: 9"; srun 943-dup
[ "$rc" -eq 2 ] && grep -q 'more than one MAX_ROUNDS' "$SB/out" && ok "a second MAX_ROUNDS line refused" || bad "rc=$rc"
[ "$(ncall)" = 0 ] && [ "$(lj 'len(L)')" = 0 ] && ok "no calls, no ledger lines from refused briefs" || bad "calls"

echo "== T7 scribe-only Johnny: no vote lines =="
stopsec 027-S1 "T7 950-johnny (saint, all claude, 1 round = 3 frontier calls)"
fresh; brief 950-johnny "${SEATS1[@]}" "MAX_ROUNDS: 1" "AGENDA: Is a four-day week worth piloting?" "SCRIBE: johnny"
cq "$OPEN"; cq $'P1: The pilot has no stated length.'; cq $'=== MERGE RECORD ===\nP1: ACCEPT - six months.\n=== ARTIFACT ===\nPosition: pilot for six months.'
srun 950-johnny; R="$FB/records/950-johnny-decision-record.md"
[ "$rc" -eq 0 ] && ok "all three roles on claude_code, Johnny named scribe (rc 0)" || bad "rc=$rc $(cat "$SB/out")"
[ "$(sj 950-johnny '[(c["capacity"],c["votes"],c.get("name")) for c in m["capacities"] if c["seat"]=="qwen_local"]')" = "[('scribe', False, 'johnny')]" ] && ok "Johnny's only capacity: scribe, votes False" || bad "$(sj 950-johnny 'm["capacities"]')"
[ "$(lj 'sum(1 for l in L if l.get("seat")=="qwen-local")')" = 0 ] && ok "no qwen-local seat lines in the main ledger (no vote cast)" || bad "ledger"
[ "$(grep -c '^| `qwen_local` |.*| votes |$' "$R")" = 0 ] && [ "$(grep -c '^| `qwen_local` | scribe: Johnny (qwen_local).*| no vote |$' "$R")" = 1 ] && ! grep -q '^#### .*(`qwen_local`)$' "$R" && ok "decision record: Johnny in one row, no vote; no position under qwen_local" || bad "$(grep '^| \|^####' "$R")"
[ "$(SL '[(l["purpose"],l["cost_source"]) for l in L if l["round"]=="950-johnny"]')" = "[('scribe-note', 'local-free')]" ] && ok "Johnny's work is on the scribe-ledger only, local-free" || bad "$(cat "$FB/records/logs/scribe-ledger.jsonl")"
endstop
fresh; brief 951-cap "${SEATS1[@]}" "MAX_ROUNDS: 2" "SCRIBE: johnny"; srun 951-cap
[ "$rc" -eq 2 ] && grep -q 'overshoot reserve' "$SB/out" && ok "(cap law unchanged: 3 frontier seats x 2 rounds = 5 calls refused under \$5)" || bad "rc=$rc"

echo "== T8 standings mechanism identical at any seat count =="
fresh; brief 952-one "RULESET: saint" "SEAT proposer: qwen_local" "SEAT challenger: qwen_local" "SEAT chair: qwen_local" "MAX_ROUNDS: 2" "SCRIBE: johnny"
qq "$OPEN"; qq $'P1: The pilot has no stated length.'; qq $'=== MERGE RECORD ===\nP1: ACCEPT - six months.\n=== ARTIFACT ===\nPosition: pilot for six months.'; qq "One point raised and accepted; none open."; qq "NO SUBSTANTIVE POINTS"
srun 952-one; D=$(S 952-one)
[ "$rc" -eq 0 ] && [ "$(sj 952-one 'm["status"]')" = converged ] && grep -q 'standings before round 2: scribe exit 0' "$D/session.log" && ok "1-seat room: standings turn before round 2, converged" || bad "rc=$rc $(cat "$SB/out")"
H1=$(heads "$D/r2-standings.md" | tr '\n' '|')
[ "$H1" = "## Positions per seat|## Points answered vs open|## Disagreements outstanding|## Scribe's reading (restates the tally; no vote)|" ] && ok "same four sections as the 2-seat room (T3)" || bad "$H1"
grep -q '^### qwen_local (proposer, challenger, chair; also scribe: Johnny' "$D/r2-standings.md" && [ "$(grep -c '^### ' "$D/r2-standings.md")" = 1 ] && ok "one seat, all capacities labelled on it" || bad "$(grep '^###' "$D/r2-standings.md")"
grep -q 'Raised 1; answered 1 (accepted 1, rejected 0); open 0.' "$D/r2-standings.md" && grep -q 'None: no point has been rejected.' "$D/r2-standings.md" && ok "1-seat tally computed the same way" || bad "$(cat "$D/r2-standings.md")"
[ "$(SL '[l["cost_source"] for l in L if l["purpose"]=="standings"]')" = "['local-free']" ] && ok "same scribe ledger line, local-free" || bad "sl"

echo "== T9 the chair never merges: decision record says so =="
stopsec 027-S1 "T9 960-none (saint, all claude, 1 round = 3 frontier calls)"
fresh; brief 960-none "${SEATS1[@]}" "MAX_ROUNDS: 1"; cq "$OPEN"; cq "NO SUBSTANTIVE POINTS"; srun 960-none
R="$FB/records/960-none-decision-record.md"
[ "$rc" -eq 0 ] && grep -q 'The chair made no synthesis' "$R" && grep -q 'No dissent on record' "$R" && [ "$(tail -1 "$R")" = "SAINT decision record: agreement, not verification." ] && ok "no merge: no synthesis claimed, no dissent, stamp kept" || bad "rc=$rc $(cat "$R" 2>/dev/null | head)"
[ ! -e "$(S 960-none)/r1-standings.md" ] && ok "one round: no standings turn" || bad "standings"

endstop
echo
if [ "$stopped" -gt 0 ]; then
  echo "known-failing-pending-ruling (027-S1: SAINT per-call cap vs overshoot reserve; Dan decides):"
  for n in "${STOPPED_NAMES[@]}"; do echo "  - $n"; done
fi
echo "phase7: $pass passed, $fail failed, $stopped known-failing-pending-ruling"
[ "$fail" -eq 0 ] || exit 1
[ "$stopped" -eq 0 ] || exit 2   # green except the named stopped checks
