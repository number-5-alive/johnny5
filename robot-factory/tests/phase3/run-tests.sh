#!/usr/bin/env bash
# Phase 3 sandbox tests (task 009). Phase 2 style: a throwaway fake HOME
# under tests/phase3/sandbox/, the factory's files copied in, the real runner
# run against stubs. Two stubs: a stub claude (CLAUDE_BIN) and a stub Ollama
# HTTP server on a 127.0.0.1 port (OLLAMA_URL, port-only test hook). Fixture
# ledgers exist ONLY in the sandbox. The real Ollama is NOT touched here;
# the live demonstrations are tests/phase3/live.sh.
# Usage: run-tests.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HOME/robot-factory"
SB="$HERE/sandbox"; FB="$SB/home/robot-factory"
pass=0; fail=0
ok()  { echo "  PASS: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }

# ---- stub Ollama: behaviour from $SB/mode, every request body to $SB/reqs ----
cat > "$HERE/.stub-ollama.py" <<'PY'
import http.server, json, os, sys
sb = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with open(os.path.join(sb, "reqs"), "a") as f: f.write(body.decode() + "\n")
        mode = open(os.path.join(sb, "mode")).read().strip()
        r = {"model": "qwen3.6:27b", "message": {"role": "assistant", "content": "stub local reply"},
             "done": True, "done_reason": "stop", "prompt_eval_count": 120, "eval_count": 30,
             "total_duration": 500000000, "load_duration": 1000000,
             "prompt_eval_duration": 100000000, "eval_duration": 300000000}
        if mode == "noeval": del r["eval_count"]
        if mode == "noprompt": del r["prompt_eval_count"]
        if mode == "big": r["prompt_eval_count"] = 30000
        if mode == "length": r["done_reason"] = "length"; r["eval_count"] = 4000
        if mode == "wrongmodel": r["model"] = "qwen3-coder:30b"
        if mode == "note": r["message"]["content"] = "Task 900 was commissioned and ran once.\n\nIt delivered one file."
        out = b"not json{" if mode == "garbage" else json.dumps(r).encode()
        if mode == "http500":
            self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(os.path.join(sb, "port"), "w").write(str(s.server_address[1]))
s.serve_forever()
PY

stub_claude() {
cat > "$SB/stub-claude" <<'EOF'
#!/usr/bin/env bash
echo "CALL $*" >> "$STUB_CALLS"
echo '{"type":"result","subtype":"success","is_error":false,"result":"stub reply","total_cost_usd":0.25,"usage":{"input_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":50},"modelUsage":{"claude-opus-5-5":{"inputTokens":5,"cacheCreationInputTokens":0,"cacheReadInputTokens":0,"outputTokens":50,"costUSD":0.25}}}'
EOF
chmod +x "$SB/stub-claude"
}

PORT=; SPID=
fresh() {
  [ -n "$SPID" ] && kill "$SPID" 2>/dev/null
  rm -rf "$SB"; mkdir -p "$FB"/{queue,working,done,logs,work,seats,bin,held,approvals}
  cp "$SRC/run-next.sh" "$FB/"; cp "$SRC/seats/claude_code.sh" "$SRC/seats/qwen_local.sh" "$FB/seats/"
  cp "$SRC/bin/budget.py" "$SRC/bin/scribe.py" "$FB/bin/"; cp "$SRC/budget.yaml" "$SRC/approve.sh" "$FB/"
  chmod +x "$FB/run-next.sh" "$FB/seats/"*.sh
  : > "$FB/ledger.jsonl"; : > "$SB/calls"; : > "$SB/reqs"; echo ok > "$SB/mode"; stub_claude
  python3 -I "$HERE/.stub-ollama.py" "$SB" & SPID=$!
  for _ in $(seq 50); do [ -s "$SB/port" ] && break; sleep 0.1; done
  PORT=$(cat "$SB/port")
}
trap '[ -n "$SPID" ] && kill "$SPID" 2>/dev/null; rm -f "$HERE/.stub-ollama.py"' EXIT
mode() { echo "$1" > "$SB/mode"; }
task() { local n=$1; shift
  { echo "# $n"; for l in "$@"; do echo "$l"; done; echo; echo "## Deliverable"; echo "sandbox test"; } > "$FB/queue/$n.md"; }
run() { HOME="$SB/home" CLAUDE_BIN="$SB/stub-claude" STUB_CALLS="$SB/calls" \
        OLLAMA_URL="${URL:-http://127.0.0.1:$PORT}" bash "$FB/run-next.sh"; echo "  runner rc=$?"; }
seat() {  # direct adapter call: seat <args...>; sets rc
  echo "hello" > "$SB/p.md"; rm -f "$SB/m.json" "$SB/o.md"
  OLLAMA_URL="${URL:-http://127.0.0.1:$PORT}" "$FB/seats/qwen_local.sh" --prompt "$SB/p.md" \
    --out "$SB/o.md" --meta "$SB/m.json" "$@" 2> "$SB/err"; rc=$?; }
mj() { python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); print(eval(sys.argv[2],{"m":m}))' "$SB/m.json" "$1"; }
lj() { python3 -I -c 'import json,sys; L=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]; print(eval(sys.argv[2],{"L":L}))' "$FB/ledger.jsonl" "$1"; }
nreq() { grep -c . "$SB/reqs"; }
ncall() { grep -c '^CALL' "$SB/calls"; }

echo "== A1 (P1) contract: ok reply, meta fields, request body =="
fresh; seat
[ "$rc" -eq 0 ] && ok "rc 0" || bad "rc=$rc"
[ "$(cat "$SB/o.md")" = "stub local reply" ] && ok "reply written to --out" || bad "reply"
[ "$(mj '(m["seat"],m["model"],m["in_tokens"],m["out_tokens"],m["cost_usd"],m["cost_source"],m["exit"])')" = "('qwen-local', 'qwen3.6:27b', 120, 30, 0.0, 'local-free', 'ok')" ] \
  && ok "meta: seat, model, tokens from prompt_eval_count/eval_count, cost 0.0 local-free, exit ok" || bad "meta $(cat "$SB/m.json")"
[ "$(mj 'all(k in m and m[k] for k in ("started","finished"))')" = True ] && ok "meta started/finished" || bad "times"
[ "$(mj '(m["temperature"],m["seed"],m["num_predict"],m["cap_exceeded"],"queue_wait_s" in m["timings"])')" = "(0.2, 9, 4000, False, True)" ] \
  && ok "meta records temperature 0.2, seed, num_predict 4000, cap_exceeded false, timings" || bad "meta extras"
python3 -I - "$SB/reqs" <<'PY' && ok "request: qwen3.6:27b, non-streaming, think false, num_predict 4000, no keep_alive/num_ctx" || bad "request body"
import json,sys; r=json.loads(open(sys.argv[1]).readline())
assert r["model"]=="qwen3.6:27b" and r["stream"] is False and r["think"] is False, r
o=r["options"]; assert o["num_predict"]==4000 and o["temperature"]==0.2, o
assert "keep_alive" not in r and "num_ctx" not in o, r
PY

echo "== A2 (P1) fails closed when Ollama is unreachable =="
URL=http://127.0.0.1:1 seat
[ "$rc" -eq 3 ] && ok "rc 3" || bad "rc=$rc"
[ "$(mj '(m["exit"],m["cost_usd"],m["in_tokens"])')" = "('unreachable', None, None)" ] && ok "meta exit unreachable, no cost, no tokens" || bad "$(cat "$SB/m.json")"

echo "== A3 (P1) fails closed when tokens are missing; bad replies =="
for md in noeval noprompt; do mode $md; seat
  [ "$rc" -eq 4 ] && [ "$(mj 'm["cost_usd"]')" = None ] && ok "$md: rc 4, cost not set ($(mj 'm["exit"]'))" || bad "$md rc=$rc"; done
mode garbage; seat; [ "$rc" -eq 4 ] && ok "unparsed JSON: rc 4" || bad "garbage rc=$rc"
mode wrongmodel; seat; [ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = wrong-model ] && ok "other model answered: rc 4 wrong-model" || bad "wrongmodel rc=$rc"
mode http500; seat; [ "$rc" -eq 3 ] && ok "HTTP 500: rc 3" || bad "http500 rc=$rc"

echo "== A4 localhost only =="
mode ok; n0=$(nreq)
for u in http://10.0.0.1:11434 http://localhost.example:$PORT https://127.0.0.1:$PORT http://127.0.0.1:$PORT/x; do
  URL=$u seat; [ "$rc" -eq 3 ] && grep -q refused "$SB/err" && ok "refused $u" || bad "$u rc=$rc"; done
[ "$(nreq)" -eq "$n0" ] && ok "no request left for a refused endpoint" || bad "a request went out"

echo "== A5 (P3) output cap: num_predict, capped exit; caps cannot be raised =="
mode length; seat; [ "$rc" -eq 2 ] && [ "$(mj '(m["exit"],m["out_cap_hit"])')" = "('capped', True)" ] && ok "done_reason length: rc 2, exit capped" || bad "length rc=$rc"
mode ok; seat --max-out-tokens 1000; [ "$rc" -eq 0 ] && [ "$(tail -1 "$SB/reqs" | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["options"]["num_predict"])')" = 1000 ] && ok "--max-out-tokens 1000 lowers num_predict" || bad "lower"
seat --max-out-tokens 5000; [ "$rc" -eq 3 ] && ok "--max-out-tokens 5000 > local cap refused" || bad "raise rc=$rc"

echo "== A6 (P3) input overage flagged, never silent =="
mode big; seat
[ "$rc" -eq 0 ] && [ "$(mj 'm["cap_exceeded"]')" = True ] && grep -q 'WARNING cap_exceeded' "$SB/err" && ok "in 30000 > 24000: cap_exceeded true + stderr warning" || bad "big rc=$rc"

echo "== B1 (P2) SEAT: qwen_local routes to the local seat =="
fresh; task 901-local "SEAT: qwen_local"; run
[ "$(ncall)" -eq 0 ] && [ "$(nreq)" -eq 1 ] && ok "one Ollama request, no claude call" || bad "calls=$(ncall) reqs=$(nreq)"
[ -f "$FB/done/901-local.md" ] && ok "task in done/" || bad "done"
[ "$(lj '[(l["phase"],l["seat"]) for l in L]')" = "[('planned', 'qwen-local'), ('actual', 'qwen-local')]" ] && ok "planned + actual, seat qwen-local" || bad "$(cat "$FB/ledger.jsonl")"
[ "$(lj '(L[0]["worst_usd"],L[0]["seat_class"],L[0]["max_out_tokens"],L[1]["cost_usd"],L[1]["cost_source"],L[1]["in_tokens"],L[1]["out_tokens"],L[1]["cap_exceeded"],L[0]["call_id"]==L[1]["call_id"])')" = "(0.0, 'local', 4000, 0.0, 'local-free', 120, 30, False, True)" ] \
  && ok "planned worst 0.0 local caps; actual 0.0 local-free, real tokens, cap_exceeded false, same call_id" || bad "$(cat "$FB/ledger.jsonl")"
grep -q 'seat: qwen-local' "$FB/logs/901-local.log" && ok "log names the seat" || bad "log"

echo "== B2 (P2) no SEAT line: Claude seat exactly as before =="
fresh; task 902-plain; run
[ "$(ncall)" -eq 1 ] && [ "$(nreq)" -eq 0 ] && ok "one claude call, no Ollama request" || bad "calls=$(ncall) reqs=$(nreq)"
[ "$(lj '(L[0]["seat"],L[0]["worst_usd"],L[1]["cost_source"],"cap_exceeded" in L[1],"seat_class" in L[0])')" = "('claude-code', 10.0, 'cli-reported', False, False)" ] && ok "claude lines unchanged in shape" || bad "$(cat "$FB/ledger.jsonl")"

echo "== B3 (P2) malformed SEAT lines refused before any call =="
for v in "SEAT: qwen-local" "SEAT: qwen_local " "seat: qwen_local" "SEAT: claude" "SEAT:qwen_local"; do
  fresh; task 903-bad "$v"; run >/dev/null
  if [ "$(ncall)$(nreq)" = 00 ] && [ "$(lj 'L[-1]["phase"]')" = refused ] && [ -f "$FB/held/903-bad.md" ]; then ok "refused: '$v'"
  elif [ "$v" = "SEAT: qwen_local " ] || [ "$v" = "seat: qwen_local" ] || [ "$v" = "SEAT:qwen_local" ]; then
    # Not an exact SEAT line: not a SEAT line at all? Must not silently route local.
    [ "$(nreq)" -eq 0 ] && ok "'$v' never routes local (calls=$(ncall))" || bad "'$v' went local"
  else bad "'$v': calls=$(ncall) reqs=$(nreq) $(tail -1 "$FB/ledger.jsonl")"; fi; done
fresh; task 904-two "SEAT: qwen_local" "SEAT: qwen_local"; run >/dev/null
[ "$(ncall)$(nreq)" = 00 ] && [ "$(lj 'L[-1]["phase"]')" = refused ] && ok "two SEAT lines refused" || bad "two"

echo "== B4 (P2) local is \$0 under a near-ceiling month; Claude is refused there =="
fresh; m=$(date +%Y-%m)
echo "{\"t\":\"$m-01T00:00:00-05:00\",\"round\":\"fixture\",\"seat\":\"claude-code\",\"phase\":\"actual\",\"cost_usd\":45.0,\"call_id\":\"fx\"}" > "$FB/ledger.jsonl"
task 905-local "SEAT: qwen_local"; run >/dev/null
[ "$(nreq)" -eq 1 ] && [ "$(lj '(L[1]["phase"],L[1]["worst_usd"],L[1]["spent_before_usd"])')" = "('planned', 0.0, 45.0)" ] && ok "local runs at \$45 spent: planned worst 0.0 written" || bad "$(cat "$FB/ledger.jsonl")"
task 906-plain; run >/dev/null
[ "$(ncall)" -eq 0 ] && [ "$(lj 'L[-1]["phase"]')" = refused ] && ok "Claude task refused on the ceiling (45 + 10 > 50)" || bad "ceiling"

echo "== B5 (P3) local token cap still refuses big prompts =="
fresh; task 907-big "SEAT: qwen_local"; head -c 80000 /dev/zero | tr '\0' x >> "$FB/queue/907-big.md"; run >/dev/null
[ "$(nreq)" -eq 0 ] && [ "$(lj '(L[-1]["phase"],L[-1]["seat"])')" = "('refused', 'qwen-local')" ] && grep -q '24000' "$FB/ledger.jsonl" && ok "80k chars > local max_in_tokens 24000: refused, no request" || bad "$(tail -c 300 "$FB/ledger.jsonl")"

echo "== B6 (P3) runner: input overage reaches the ledger; output cap logged; failure leaves no actual =="
fresh; mode big; task 908-over "SEAT: qwen_local"; run >/dev/null
[ "$(lj 'L[-1]["cap_exceeded"]')" = True ] && grep -q 'WARNING: cap_exceeded' "$FB/logs/908-over.log" && ok "cap_exceeded true on the ledger line + log warning" || bad "$(tail -1 "$FB/ledger.jsonl")"
fresh; mode length; task 909-len "SEAT: qwen_local"; run >/dev/null
grep -q 'capped: the local seat stopped at its output cap' "$FB/logs/909-len.log" && [ "$(lj 'L[-1]["exit"]')" = capped ] && ok "capped run logged, actual exit capped" || bad "len"
fresh; task 910-down "SEAT: qwen_local"; out=$(URL=http://127.0.0.1:1 run)
[ "$(lj '[l["phase"] for l in L]')" = "['planned']" ] && grep -q 'NOT written' "$FB/logs/910-down.log" && ok "Ollama down: no actual line, ledger refuses ($(echo "$out" | tail -1 | tr -d ' '))" || bad "$(cat "$FB/ledger.jsonl")"
fresh; task 911-scope "SEAT: qwen_local" "SCOPE: build"; run >/dev/null
grep -q 'scope: build ignored' "$FB/logs/911-scope.log" && [ "$(ncall)" -eq 0 ] && ok "SCOPE: build on a local task: logged as ignored" || bad "scope"

echo "== C1 (P4) scribe writes only under records/, record complete and verbatim =="
fresh; mode note
task 920-demo "SEAT: qwen_local"; run >/dev/null; echo "made" > "$FB/work/920-thing.md"
sum() { (cd "$FB" && find . -path ./records -prune -o -type f -print0 | sort -z | xargs -0 sha256sum); }
before=$(sum)
HOME="$SB/home" OLLAMA_URL="http://127.0.0.1:$PORT" python3 "$FB/bin/scribe.py" 920-demo > "$SB/scribe.out" 2>&1; src=$?
[ "$src" -eq 0 ] && ok "scribe rc 0" || bad "scribe rc=$src $(cat "$SB/scribe.out")"
[ "$before" = "$(sum)" ] && ok "nothing outside records/ changed (done/, queue/, ledger.jsonl, logs/, work/)" || bad "files outside records/ changed"
R="$FB/records/920-demo-record.md"
for h in "## 1. Commission" "## 2. What ran" "## 3. Deliverables" "## 4. Ledger" "## 5. Pass marks and moderator review" "## 6. Scribe's note"; do
  grep -qxF "$h" "$R" || bad "missing $h"; done && ok "six headed parts"
[ "$(tail -1 "$R")" = "A record, not an endorsement. The scribe holds no vote." ] && ok "footer" || bad "footer"
grep -q 'PENDING MODERATOR REVIEW' "$R" && ok "pending review" || bad "pending"
python3 -I - "$R" "$FB/ledger.jsonl" "$FB/done/920-demo.md" <<'PY' && ok "Ledger section == the task's ledger.jsonl lines, byte for byte; commission verbatim" || bad "verbatim"
import json,re,sys; r=open(sys.argv[1]).read()
sec=r.split("## 4. Ledger\n",1)[1].split("## 5.",1)[0]
got=re.search(r"```jsonl\n(.*?)\n```", sec, re.S).group(1).split("\n")
want=[l.rstrip("\n") for l in open(sys.argv[2]) if json.loads(l).get("round")=="920-demo"]
assert got==want, (got,want)
assert open(sys.argv[3]).read() in r
PY
grep -q 'Task 900 was commissioned and ran once. It delivered one file.' "$R" && ok "note is one paragraph (blank line collapsed)" || bad "note"
grep -q "Drafted by the local seat \`qwen-local\` (model \`qwen3.6:27b\`, temperature 0.2" "$R" && ok "note attributed to the local seat" || bad "attribution"
grep -q '"purpose": "scribe-note"' "$FB/records/logs/scribe-ledger.jsonl" && ok "scribe's own ledger line in records/logs/" || bad "scribe ledger"

echo "== C2 scribe: no overwrite without --force; note failure is explicit =="
HOME="$SB/home" python3 "$FB/bin/scribe.py" 920-demo >/dev/null 2>&1; [ $? -eq 2 ] && ok "existing record: refused (rc 2)" || bad "overwrite"
HOME="$SB/home" OLLAMA_URL=http://127.0.0.1:1 python3 "$FB/bin/scribe.py" 920-demo --force >/dev/null 2>&1; src=$?
[ "$src" -eq 3 ] && grep -q 'Note not drafted' "$R" && ok "Ollama down: rc 3, record says 'Note not drafted'" || bad "note fail rc=$src"
HOME="$SB/home" python3 "$FB/bin/scribe.py" 999-none >/dev/null 2>&1; [ $? -eq 2 ] && ok "no done/ file: refused" || bad "nodone"
HOME="$SB/home" python3 "$FB/bin/scribe.py" ../etc >/dev/null 2>&1; [ $? -eq 2 ] && ok "bad task name refused" || bad "name"
rm -rf "$FB/records"; ln -s "$FB/done" "$FB/records"
HOME="$SB/home" OLLAMA_URL="http://127.0.0.1:$PORT" python3 "$FB/bin/scribe.py" 920-demo >/dev/null 2>&1; src=$?
[ "$src" -eq 2 ] && [ ! -e "$FB/done/920-demo-record.md" ] && ok "records/ symlinked into done/: refused, nothing written" || bad "symlink rc=$src"

echo "== D1 (009b, P2) same task name twice: both metas and both logs survive =="
fresh; task 930-twice; run; mv "$FB/done/930-twice.md" "$FB/queue/"; run   # back to back: same second is possible
n=$(ls "$FB"/logs/930-twice@*.meta.json 2>/dev/null | wc -l)
[ "$n" -eq 2 ] && ok "two per-call metas: $(cd "$FB" && echo logs/930-twice@*.meta.json)" || bad "metas: $n"
[ "$(ls "$FB"/logs/930-twice@*.log | wc -l)" -eq 2 ] && ok "two per-call logs" || bad "per-call logs"
[ "$(lj 'len({l["meta"] for l in L if l["phase"]=="actual" and l["round"]=="930-twice"})')" = 2 ] && \
[ "$(lj 'len({l["call_id"] for l in L if l["phase"]=="actual"})')" = 2 ] && ok "two actual lines, distinct meta paths and call_ids" || bad "ledger"
[ "$(lj 'all(l["call_id"]=="930-twice@"+__import__("json").load(open("'"$FB"'/"+l["meta"]))["started"] for l in L if l["phase"]=="actual")')" = True ] && \
  ok "each meta's start time is its call_id's time" || bad "stamp/call_id mismatch"
[ "$(grep -c '^call: 930-twice@' "$FB/logs/930-twice.log")" -eq 2 ] && ok "logs/930-twice.log is append-only: holds both calls" || bad "per-task log"
for m in "$FB"/logs/930-twice@*.meta.json; do echo "  $(basename "$m"): $(cat "$m")"; done

echo "== D2 (009b, P3) a seat editing run-next.sh in place mid-run: the run completes =="
# 026b: the SCOPE: build line was dropped from 931-selfedit (now Dan-only build-write);
# the stub performs the edit itself, so the test does not depend on the grant.
stub_edit() {  # written after fresh(), which wipes $SB
cat > "$SB/stub-claude-edit" <<'EOF'
#!/usr/bin/env bash
# rewrite the runner IN PLACE (same inode, truncate + write) like a seat's edit tool would
{ for i in $(seq 9000); do echo; done; echo 'echo CORRUPTED; exit 42'; } > "$EDIT_TARGET"
echo "CALL $*" >> "$STUB_CALLS"
echo '{"type":"result","subtype":"success","is_error":false,"result":"edited the runner","total_cost_usd":0.25,"usage":{"input_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":50},"modelUsage":{"claude-opus-5-5":{"inputTokens":5,"cacheCreationInputTokens":0,"cacheReadInputTokens":0,"outputTokens":50,"costUSD":0.25}}}'
EOF
chmod +x "$SB/stub-claude-edit"
}
editrun() { stub_edit; mkdir -p "$SB/tmp"; HOME="$SB/home" TMPDIR="$SB/tmp" CLAUDE_BIN="$SB/stub-claude-edit" STUB_CALLS="$SB/calls" \
  EDIT_TARGET="$FB/$1" bash "$FB/$1" > "$SB/out" 2>&1; rc=$?; cat "$SB/out" | sed 's/^/  | /'; }
fresh; task 931-selfedit; ino=$(stat -c %i "$FB/run-next.sh"); editrun run-next.sh
[ "$rc" -eq 0 ] && ! grep -q CORRUPTED "$SB/out" && ok "runner rc=0, never ran the edited text" || bad "rc=$rc"
[ "$(lj 'sum(1 for l in L if l["phase"]=="actual" and l["round"]=="931-selfedit")')" = 1 ] && ok "actual line written" || bad "no actual line"
[ -f "$FB/done/931-selfedit.md" ] && ok "task moved to done/" || bad "not done"
grep -q CORRUPTED "$FB/run-next.sh" && [ "$(stat -c %i "$FB/run-next.sh")" = "$ino" ] && ok "the seat's in-place edit landed (same inode) and persists" || bad "edit not applied"
[ -z "$(ls -A "$SB/tmp")" ] && ok "private copy removed on exit" || bad "private copy left: $(ls "$SB/tmp")"
echo "  control: the pre-009b runner under the same stub"
fresh; task 931-selfedit; cp "$SRC/run-next.sh.bak-pre-009b-20261031" "$FB/run-next.old.sh"; editrun run-next.old.sh
grep -q CORRUPTED "$SB/out" && [ "$(lj 'sum(1 for l in L if l["phase"]=="actual")')" = 0 ] && \
  ok "control reproduces 009's failure: old runner executes the edit (rc=$rc), no actual line" || bad "control did not reproduce"

echo "== D3 (009b) adapters refuse an existing --meta: exit 3, file untouched, no model call =="
fresh; echo keep > "$SB/m.json"
echo "hello" > "$SB/p.md"; OLLAMA_URL="http://127.0.0.1:$PORT" "$FB/seats/qwen_local.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2> "$SB/err"; rc=$?
[ "$rc" -eq 3 ] && [ "$(cat "$SB/m.json")" = keep ] && [ "$(nreq)" -eq 0 ] && ok "qwen_local.sh: rc 3, meta kept, 0 requests ($(cat "$SB/err"))" || bad "qwen rc=$rc"
CLAUDE_BIN="$SB/stub-claude" STUB_CALLS="$SB/calls" "$FB/seats/claude_code.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2> "$SB/err"; rc=$?
[ "$rc" -eq 3 ] && [ "$(cat "$SB/m.json")" = keep ] && [ ! -s "$SB/calls" ] && ok "claude_code.sh: rc 3, meta kept, 0 calls ($(cat "$SB/err"))" || bad "claude rc=$rc"
ln -s "$SB/nowhere" "$SB/m2.json"
OLLAMA_URL="http://127.0.0.1:$PORT" "$FB/seats/qwen_local.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m2.json" 2>/dev/null; rc=$?
[ "$rc" -eq 3 ] && [ ! -e "$SB/nowhere" ] && ok "dangling symlink as --meta: refused, nothing written through it" || bad "symlink rc=$rc"
python3 -I "$FB/bin/budget.py" preflight "$FB" "$FB/queue/x.md" x "yesterday" >/dev/null 2>&1; [ $? -eq 2 ] && ok "budget.py preflight: malformed call time refused (rc 2)" || bad "preflight t0"

echo "TOTAL: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
