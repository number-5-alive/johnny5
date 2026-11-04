#!/usr/bin/env bash
# Phase 10 sandbox tests (task 026b): tiered scope approval.
# Fake HOME under tests/phase10/sandbox/; the real runner, adapter, budget.py
# and moderator_approve.py run against a stub CLI that records argv.
# Every approval record here (Dan fixture or moderator) exists ONLY in the sandbox.
# Usage: run-tests.sh   (tests the installed files under ~/robot-factory)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HOME/robot-factory"
SB="$HERE/sandbox"; FB="$SB/home/robot-factory"
pass=0; fail=0
ok()  { echo "  PASS: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }

stub() {
cat > "$SB/stub-claude" <<'EOF'
#!/usr/bin/env bash
{ printf 'CALL'; for a in "$@"; do printf ' [%s]' "$(printf '%s' "$a" | tr '\n' ' ' | head -c 120)"; done; echo " RF_SEAT_RUN=${RF_SEAT_RUN:-unset}"; } >> "$STUB_CALLS"
echo '{"type":"result","subtype":"success","is_error":false,"result":"stub reply","total_cost_usd":0.25,"usage":{"input_tokens":5,"cache_creation_input_tokens":100,"cache_read_input_tokens":1000,"output_tokens":50},"modelUsage":{"claude-opus-5-5":{"inputTokens":5,"cacheCreationInputTokens":100,"cacheReadInputTokens":1000,"outputTokens":50,"costUSD":0.25}}}'
EOF
chmod +x "$SB/stub-claude"
}
fresh() {
  rm -rf "$SB"; mkdir -p "$FB"/{queue,working,done,logs,work,seats,bin,held,approvals,secrets} "$SB/home/.claude/projects"
  cp "$SRC/run-next.sh" "$FB/"; cp "$SRC/seats/claude_code.sh" "$FB/seats/"
  cp "$SRC/bin/budget.py" "$SRC/bin/moderator_approve.py" "$FB/bin/"; cp "$SRC/budget.yaml" "$SRC/approve.sh" "$FB/"
  chmod +x "$FB/run-next.sh" "$FB/seats/claude_code.sh"
  : > "$FB/ledger.jsonl"; stub; : > "$SB/calls"
}
task() { local n=$1; shift
  { echo "# $n"; for l in "$@"; do echo "$l"; done; echo; echo "## Deliverable"; echo "sandbox test"; } > "$FB/queue/$n.md"
  touch -d '-5 seconds' "$FB/queue/$n.md"; }
run() { HOME="$SB/home" CLAUDE_BIN="$SB/stub-claude" STUB_CALLS="$SB/calls" bash "$FB/run-next.sh" > "$SB/out" 2>&1; rc=$?; sed 's/^/  | /' "$SB/out"; }
calls() { grep -c '^CALL' "$SB/calls"; }
lastline() { tail -1 "$FB/ledger.jsonl"; }
modapp() { HOME="$SB/home" python3 -I "$FB/bin/moderator_approve.py" "$@"; }
dan_fixture() {  # Dan's approval record, written the way approve.sh writes it (sandbox only)
  python3 -I - "$FB/approvals/$1.jsonl" "$1" "$FB/queue/$1.md" <<'PY'
import hashlib, json, sys, time
out, name, f = sys.argv[1:]
ep = time.time()
rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ep)), "epoch": ep, "name": name, "target": f,
       "sha256": hashlib.sha256(open(f, "rb").read()).hexdigest(), "cap_usd": None, "tty": "FIXTURE", "user": "fixture"}
open(out, "a").write(json.dumps(rec) + "\n")
PY
}
ran()     { [ "$(calls)" -eq 1 ] && [ -f "$FB/done/$1.md" ] && lastline | grep -q '"phase": *"actual"'; }
refused() { [ "$(calls)" -eq 0 ] && [ -f "$FB/held/$1.md" ] && lastline | grep -q '"phase": *"refused"'; }

echo "== P1 build-read + moderator approval -> runs, enumerated read grant =="
fresh; task 201-read "SCOPE: build-read"
modapp "$FB/queue/201-read.md" --commission "Dan's commission 2026-11-02: read the service source" && ok "moderator_approve.py wrote a record" || bad "tool rc"
run
ran 201-read && ok "ran: one model call, done/, actual line" || bad "did not run"
grep -q '^approval: moderator [0-9.]*$' "$FB/logs/201-read.log" && ok "log: $(grep '^approval:' "$FB/logs/201-read.log")" || bad "approval log line"
grep -q -- '\[--permission-prompts\] \[none\] \[--settings\]' "$SB/calls" && ok "prompts off + settings passed" || bad "grant args"
grep -q -- "\[--add-dir\] \[$FB/logs\]" "$SB/calls" && grep -q -- "\[--add-dir\] \[$SB/home/.claude/projects\]" "$SB/calls" && ok "enumerated read dirs added (logs/, usage records)" || bad "add-dir"
grep -Eq -- "\[--add-dir\] \[$FB(/approvals|/approvals-moderator|/secrets)?\]" "$SB/calls" && bad "factory root or approvals/secrets added" || ok "no --add-dir for the root, approvals/, approvals-moderator/, secrets/"
grep -q 'allowedTools' "$SB/calls" && bad "Bash pre-approved on build-read" || ok "no --allowedTools Bash on build-read"
G=$(ls "$FB"/logs/201-read@*.grant.json)
python3 -I - "$G" "$FB" <<'PY' && ok "grant: approvals dirs + secrets denied, never allowed; Edit allowed only in work/" || bad "grant content"
import json, sys; g = json.load(open(sys.argv[1]))["permissions"]; fb = sys.argv[2]
for d in ("approvals", "approvals-moderator", "secrets"):
    p = "/" + fb + "/" + d
    assert not any(r.startswith(("Read(" + p + "/", "Read(" + p + ")", "Edit(" + p)) for r in g["allow"]), d
    assert "Read(%s/**)" % p in g["deny"] and "Edit(%s/**)" % p in g["deny"], d
assert [r for r in g["allow"] if r.startswith("Edit(")] == ["Edit(/%s/work/**)" % fb], g["allow"]
PY
grep -q 'RF_SEAT_RUN=1' "$SB/calls" && ok "seat call runs with RF_SEAT_RUN=1" || bad "RF_SEAT_RUN"
grep -q '"approver": *"moderator"' "$FB/ledger.jsonl" && ok "planned line names approver moderator" || bad "ledger approver"

echo "== P2 build-read + Dan approval only -> runs =="
fresh; task 202-read "SCOPE: build-read"; dan_fixture 202-read; run
ran 202-read && grep -q '^approval: dan [0-9.]*$' "$FB/logs/202-read.log" && ok "ran; log: $(grep '^approval:' "$FB/logs/202-read.log")" || bad "dan build-read"

echo "== P3 build-read + no approval -> refused, names both approvals =="
fresh; task 203-read "SCOPE: build-read"; run
refused 203-read && ok "refused: zero calls, held/, refused line" || bad "not refused"
grep -q 'moderator approval (bin/moderator_approve.py' "$SB/out" && grep -q "Dan's approval (approve.sh" "$SB/out" && ok "message names which approval would satisfy it" || bad "message"

echo "== P4 build-read + moderator approval, then the file is edited -> refused =="
fresh; task 204-read "SCOPE: build-read"; modapp "$FB/queue/204-read.md" --commission "c" >/dev/null
echo "one more line" >> "$FB/queue/204-read.md"; run
refused 204-read && grep -q 'moderator: hash mismatch' "$SB/out" && ok "edit voids the moderator record (hash mismatch)" || bad "edited file ran"
fresh; task 204b-read "SCOPE: build-read"; modapp "$FB/queue/204b-read.md" --commission "c" >/dev/null
touch -d '+5 seconds' "$FB/queue/204b-read.md"; run
refused 204b-read && grep -q 'not newer than' "$SB/out" && ok "record older than the file's mtime -> refused" || bad "stale record ran"

echo "== P5 build-write + moderator approval only -> refused =="
fresh; task 205-write "SCOPE: build-write"
modapp "$FB/queue/205-write.md" --commission "c" 2> "$SB/err"; mrc=$?
[ "$mrc" -ne 0 ] && [ ! -e "$FB/approvals-moderator/205-write.jsonl" ] && ok "tool refuses build-write ($(cat "$SB/err"))" || bad "tool approved build-write"
python3 -I - "$FB/approvals-moderator/205-write.jsonl" "$FB/queue/205-write.md" <<'PY'
import hashlib, json, os, sys, time
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
rec = {"t": "x", "epoch": time.time(), "name": "205-write", "target": sys.argv[2], "approver": "moderator", "commission": "c",
       "sha256": hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest(), "cap_usd": None}
open(sys.argv[1], "a").write(json.dumps(rec) + "\n")
PY
run
refused 205-write && grep -q 'never by a moderator approval (a valid moderator record exists and does not count)' "$SB/out" && ok "a hand-made valid moderator record does not satisfy build-write" || bad "build-write ran on moderator"

echo "== P6 build-write + Dan approval -> runs with the pre-026b widened grant =="
fresh; task 206-write "SCOPE: build-write"; dan_fixture 206-write; run
ran 206-write && grep -q -- "\[--add-dir\] \[$FB\] \[$SB/home/.claude/projects\] \[--allowedTools\] \[Bash\]" "$SB/calls" \
  && grep -q '^approval: dan ' "$FB/logs/206-write.log" && ok "ran, widened args, approval: dan logged" || bad "build-write+dan"

echo "== P7 legacy SCOPE: build + moderator approval -> refused =="
fresh; task 207-legacy "SCOPE: build"
modapp "$FB/queue/207-legacy.md" --commission "c" 2>/dev/null && bad "tool approved legacy" || ok "tool refuses legacy SCOPE: build"
cp "$FB/queue/207-legacy.md" "$SB/t.md"; sed -i 's/^SCOPE: build$/SCOPE: build-read/' "$SB/t.md"
python3 -I - "$FB/approvals-moderator/207-legacy.jsonl" "$FB/queue/207-legacy.md" <<'PY'
import hashlib, json, os, sys, time
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
rec = {"t": "x", "epoch": time.time(), "name": "207-legacy", "target": sys.argv[2], "approver": "moderator", "commission": "c",
       "sha256": hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest(), "cap_usd": None}
open(sys.argv[1], "a").write(json.dumps(rec) + "\n")
PY
run
refused 207-legacy && grep -q 'build-write is satisfied only by Dan' "$SB/out" && ok "legacy reads as build-write: moderator record refused" || bad "legacy ran"
fresh; task 207b-legacy "SCOPE: build"; dan_fixture 207b-legacy; run
ran 207b-legacy && ok "legacy SCOPE: build + Dan approval still runs" || bad "legacy+dan"

echo "== P8 a moderator record forged inside work/ -> ignored, refused =="
fresh; task 208-forge "SCOPE: build-read"
mkdir -p "$FB/work/approvals-moderator"
python3 -I - "$FB/work/approvals-moderator/208-forge.jsonl" "$FB/queue/208-forge.md" <<'PY'
import hashlib, json, sys, time
rec = {"t": "x", "epoch": time.time(), "name": "208-forge", "target": sys.argv[2], "approver": "moderator", "commission": "forged",
       "sha256": hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest(), "cap_usd": None}
for p in (sys.argv[1], sys.argv[1].replace("/approvals-moderator", "")):
    open(p, "a").write(json.dumps(rec) + "\n")
PY
run
refused 208-forge && ok "records in work/ and work/approvals-moderator/ are ignored" || bad "forged record honoured"
fresh; task 208b-forge "SCOPE: build-read"; mkdir -p "$FB/work/fake"
HOME="$SB/home" python3 -I "$FB/bin/moderator_approve.py" "$FB/queue/208b-forge.md" --commission c >/dev/null
mv "$FB/approvals-moderator/208b-forge.jsonl" "$FB/work/fake/"; rmdir "$FB/approvals-moderator"
ln -s "$FB/work/fake" "$FB/approvals-moderator"; run
refused 208b-forge && grep -q 'symlink' "$SB/out" && ok "approvals-moderator/ symlinked into work/ -> refused" || bad "symlinked dir honoured"
fresh; task 208c-forge "SCOPE: build-read"; mkdir -p "$FB/approvals-moderator"
python3 -I - "$FB/approvals-moderator/208c-forge.jsonl" "$FB/queue/208c-forge.md" <<'PY'
import hashlib, json, sys, time
rec = {"t": "x", "epoch": time.time(), "name": "208c-forge", "target": sys.argv[2], "sha256": hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest()}
open(sys.argv[1], "a").write(json.dumps(rec) + "\n")
PY
run
refused 208c-forge && grep -q 'not a moderator approval' "$SB/out" && ok "record without approver/commission refused" || bad "bare record honoured"

echo "== P9 confined task -> unchanged =="
fresh; task 209-plain; run
ran 209-plain && ! grep -q -- '--add-dir\|allowedTools\|permission-prompts\|--settings' "$SB/calls" && ! grep -q '^approval:' "$FB/logs/209-plain.log" \
  && ok "ran with no scope args, no approval line" || bad "confined changed"
grep -q 'claude-code confined -$' "$FB/logs/209-plain.log" && ok "PLAN fields 8-9: confined -" || bad "PLAN tail"

echo "== P10 header parsing and the moderator tool's refusals =="
fresh; task 210-bad "SCOPE: build-everything"; run
refused 210-bad && grep -q 'SCOPE line not recognised' "$SB/out" && ok "unknown SCOPE value refused" || bad "unknown scope"
fresh; task 211-two "SCOPE: build-read" "SCOPE: build-read"; run
refused 211-two && grep -q 'more than one SCOPE line' "$SB/out" && ok "repeated SCOPE refused" || bad "two scopes"
fresh; task 212-read "SCOPE: build-read"
modapp "$FB/queue/212-read.md" 2>/dev/null; [ $? -ne 0 ] && ok "no --commission -> refused" || bad "no commission"
modapp "$FB/queue/212-read.md" --commission "  " 2>/dev/null; [ $? -ne 0 ] && ok "empty --commission -> refused" || bad "empty commission"
RF_SEAT_RUN=1 modapp "$FB/queue/212-read.md" --commission c 2>/dev/null; [ $? -ne 0 ] && [ ! -e "$FB/approvals-moderator/212-read.jsonl" ] && ok "RF_SEAT_RUN set -> refused, nothing written" || bad "ran inside seat env"
modapp "$FB/queue/212-read.md" --commission "first" >/dev/null; modapp "$FB/queue/212-read.md" --commission "second" >/dev/null
python3 -I - "$FB/approvals-moderator/212-read.jsonl" <<'PY' && ok "append-only, record fields exact" || bad "record shape"
import json, sys; L = [json.loads(l) for l in open(sys.argv[1])]
assert len(L) == 2 and [r["commission"] for r in L] == ["first", "second"]
assert all(set(r) == {"t", "epoch", "name", "target", "sha256", "cap_usd", "approver", "commission"} and r["approver"] == "moderator" for r in L)
PY
fresh; task 213-sea "SEAT: qwen_local" "SCOPE: build-write" 2>/dev/null
HOME="$SB/home" python3 -I "$FB/bin/budget.py" preflight "$FB" "$FB/queue/213-sea.md" 213-sea > "$SB/out"; prc=$?
[ "$prc" -eq 0 ] && grep -q ' qwen-local confined -$' "$SB/out" && ok "word-only seat: SCOPE needs no approval, widens nothing (unchanged)" || bad "word-only: $(cat "$SB/out")"
fresh; task 214-capread "SCOPE: build-read" "CAP_USD: 25"; modapp "$FB/queue/214-capread.md" --commission c >/dev/null 2>&1; run
refused 214-capread && grep -q 'approval required but none found (approvals/214-capread.jsonl)' "$SB/out" && ok "cap override stays Dan-only even with a moderator record" || bad "cap override on moderator"

echo "== P11 budget.py summary lists moderator approvals =="
fresh; task 215-read "SCOPE: build-read"; modapp "$FB/queue/215-read.md" --commission c >/dev/null
python3 -I "$FB/bin/budget.py" summary "$FB" > "$SB/out"
grep -q "^moderator approvals on file (build-read only, all months): 215-read $(date +%Y-%m-%d)$" "$SB/out" && ok "$(tail -1 "$SB/out")" || bad "summary: $(cat "$SB/out")"
fresh; python3 -I "$FB/bin/budget.py" summary "$FB" | tail -1 | grep -q ': none$' && ok "summary says none when none" || bad "summary none"

echo; echo "TOTAL: $pass pass, $fail fail"
rm -rf "$SB"
[ "$fail" -eq 0 ]
