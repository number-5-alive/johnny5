#!/usr/bin/env bash
# Phase 5 sandbox tests (task 012). Phase 3 style: a throwaway fake HOME under
# tests/phase5/sandbox/, the factory's files copied in, the real runner and
# adapters run against STUB CLIs (CODEX_BIN, GEMINI_BIN, CLAUDE_BIN test
# hooks). No live login, no model call, no network. The real codex/gemini
# are touched once at the end, only to show the live no-auth refusal
# (login status / missing creds), which makes no model call.
# Usage: run-tests.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HOME/robot-factory"
SB="$HERE/sandbox"; FB="$SB/home/robot-factory"
pass=0; fail=0
ok()  { echo "  PASS: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }

stubs() {
cat > "$SB/stub-codex" <<'EOF'
#!/usr/bin/env bash
mode=$(cat "$SB_DIR/mode")
if [ "$1 $2" = "login status" ]; then
  [ "$mode" = noauth ] && { echo "Not logged in"; exit 1; }
  echo "Logged in using ChatGPT"; exit 0; fi
echo "CALL codex $*" >> "$STUB_CALLS"; cat > "$SB_DIR/stdin"
case "$mode" in
  hang) sleep 30;;
  error) echo '{"type":"error","message":"stream error"}'; exit 1;;
  notok) echo '{"type":"item.completed","item":{"id":"i0","type":"agent_message","text":"stub codex reply"}}';;
  *) out=50; [ "$mode" = big ] && out=50000
     echo '{"type":"thread.started","thread_id":"t"}'
     echo '{"type":"item.completed","item":{"id":"i0","type":"agent_message","text":"stub codex reply"}}'
     echo '{"type":"turn.completed","usage":{"input_tokens":1200,"cached_input_tokens":200,"output_tokens":'$out',"reasoning_output_tokens":10}}';;
esac
EOF
cat > "$SB/stub-gemini" <<'EOF'
#!/usr/bin/env bash
mode=$(cat "$SB_DIR/mode")
echo "CALL gemini $*" >> "$STUB_CALLS"; cat > "$SB_DIR/stdin"
case "$mode" in
  hang) sleep 30;;
  noauth41) echo '{"error":{"type":"Error","message":"auth required","code":41}}'; exit 41;;
  notok) echo '{"response":"stub gemini reply","stats":{"models":{}}}';;
  *) c=40; [ "$mode" = big ] && c=40000
     echo '{"response":"stub gemini reply","stats":{"models":{"gemini-3-pro":{"tokens":{"input":800,"prompt":900,"candidates":'$c',"total":1000,"cached":100,"thoughts":5,"tool":0}}}}}';;
esac
EOF
cat > "$SB/stub-claude" <<'EOF'
#!/usr/bin/env bash
echo "CALL claude $*" >> "$STUB_CALLS"
echo '{"type":"result","subtype":"success","is_error":false,"result":"stub reply","total_cost_usd":0.25,"usage":{"input_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":50},"modelUsage":{"claude-opus-5-5":{"inputTokens":5,"cacheCreationInputTokens":0,"cacheReadInputTokens":0,"outputTokens":50,"costUSD":0.25}}}'
EOF
chmod +x "$SB"/stub-*
}
fresh() {
  rm -rf "$SB"; mkdir -p "$FB"/{queue,working,done,logs,work,seats/cards,bin,held,approvals} "$SB/home/.gemini"
  cp "$SRC/run-next.sh" "$SRC/budget.yaml" "$SRC/approve.sh" "$FB/"
  cp "$SRC"/seats/*.sh "$SRC/seats/token_seat.py" "$SRC/seats/registry.json" "$FB/seats/"
  cp "$SRC"/seats/cards/*.md "$FB/seats/cards/"
  cp "$SRC/bin/budget.py" "$SRC/bin/session.py" "$FB/bin/"
  chmod +x "$FB/run-next.sh" "$FB/seats/"*.sh
  echo '{}' > "$SB/home/.gemini/oauth_creds.json"     # stub login (fake HOME only)
  : > "$FB/ledger.jsonl"; : > "$SB/calls"; echo ok > "$SB/mode"; stubs
  setmodel gpt-stub
}
setmodel() { python3 -I - "$FB/seats/registry.json" "$1" <<'PY'
import json,sys; p,mdl=sys.argv[1:]; r=json.load(open(p))
r["seats"]["codex"]["model"]=None if mdl=="null" else mdl; json.dump(r,open(p,"w"))
PY
}
mode() { echo "$1" > "$SB/mode"; }
ENV=(env -u OPENAI_API_KEY -u CODEX_API_KEY -u GEMINI_API_KEY -u GOOGLE_API_KEY -u GOOGLE_GENAI_USE_VERTEXAI)
envs() { "${ENV[@]}" HOME="$SB/home" SB_DIR="$SB" STUB_CALLS="$SB/calls" CODEX_BIN="$SB/stub-codex" \
         GEMINI_BIN="$SB/stub-gemini" CLAUDE_BIN="$SB/stub-claude" "$@"; }
seat() {  # seat <codex|gemini_cli> [args]: direct adapter call; sets rc, secs
  local k=$1; shift; echo "hello from the prompt" > "$SB/p.md"; rm -f "$SB/m.json" "$SB/o.md"
  local t=$(date +%s.%N)
  envs "$FB/seats/$k.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" "$@" 2> "$SB/err"; rc=$?
  secs=$(python3 -c "print(round($(date +%s.%N)-$t,1))"); }
mj() { python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); print(eval(sys.argv[2],{"m":m}))' "$SB/m.json" "$1"; }
lj() { python3 -I -c 'import json,sys; L=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]; print(eval(sys.argv[2],{"L":L}))' "$FB/ledger.jsonl" "$1"; }
ncall() { grep -c '^CALL' "$SB/calls"; }
nled() { grep -c . "$FB/ledger.jsonl"; }
task() { local n=$1; shift
  { echo "# $n"; for l in "$@"; do echo "$l"; done; echo; echo "## Deliverable"; echo "sandbox test"; } > "$FB/queue/$n.md"; }
run() { envs bash "$FB/run-next.sh" > "$SB/run.out"; rrc=$?; }
trap 'rm -rf "$SB"' EXIT

echo "== A (P1) no auth: fast refusal, no model call, meta written, no ledger line =="
for k in codex gemini_cli; do
  fresh; [ $k = codex ] && mode noauth || rm "$SB/home/.gemini/oauth_creds.json"
  seat $k
  [ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = no-auth ] && ok "$k: rc 3, exit no-auth ($(head -c 90 "$SB/err"))" || bad "$k rc=$rc $(cat "$SB/m.json")"
  python3 -c "import sys; sys.exit(0 if $secs < 5 else 1)" && ok "$k: refused in ${secs}s (no hang)" || bad "$k slow: ${secs}s"
  [ "$(ncall)" -eq 0 ] && [ "$(nled)" -eq 0 ] && [ -e "$SB/o.md" ] && [ ! -s "$SB/o.md" ] && ok "$k: no model call, no ledger line, empty --out" || bad "$k calls/ledger"
  [ "$(mj '(m["cost_usd"],m["in_tokens"],m["out_tokens"])')" = "(None, None, None)" ] && ok "$k: meta carries no cost and no tokens" || bad "$k meta"
done
fresh; mode noauth41; seat gemini_cli
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = no-auth ] && ok "gemini creds present but CLI says code 41: rc 3 no-auth" || bad "41 rc=$rc"

echo "== B (P1) fail closed: API key set, codex model unnamed, existing meta, timeout =="
fresh; for k in codex gemini_cli; do
  key=OPENAI_API_KEY; [ $k = gemini_cli ] && key=GEMINI_API_KEY
  echo hi > "$SB/p.md"; rm -f "$SB/m.json"
  envs env $key=sk-test "$FB/seats/$k.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
  [ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = api-key-refused ] && [ "$(ncall)" -eq 0 ] && ok "$k: $key set: refused rc 3, no call" || bad "$k apikey rc=$rc"
done
setmodel null; seat codex
[ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = model-missing ] && [ "$(ncall)" -eq 0 ] && ok "codex with registry model null: rc 4 model-missing, no call" || bad "model rc=$rc"
setmodel gpt-stub
for k in codex gemini_cli; do
  echo '{"keep":1}' > "$SB/m.json"
  envs "$FB/seats/$k.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
  [ "$rc" -eq 3 ] && [ "$(cat "$SB/m.json")" = '{"keep":1}' ] && [ "$(ncall)" -eq 0 ] && ok "$k: existing meta refused, untouched, no call" || bad "$k meta rc=$rc"
done
mode hang; for k in codex gemini_cli; do
  rm -f "$SB/m.json"; t=$(date +%s)
  TIMEOUT_S=2 envs "$FB/seats/$k.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
  [ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = timeout ] && [ $(( $(date +%s) - t )) -lt 10 ] && ok "$k: hung CLI stopped by timeout, rc 3" || bad "$k hang rc=$rc"
done

echo "== C (P1) success: tokens only from the CLI, no dollar figure =="
fresh; seat codex
[ "$rc" -eq 0 ] && [ "$(cat "$SB/o.md")" = "stub codex reply" ] && ok "codex: rc 0, reply written" || bad "codex rc=$rc $(cat "$SB/err")"
[ "$(mj '(m["model"],m["model_source"],m["in_tokens"],m["out_tokens"],m["cost_usd"],m["cost_source"],m["billing"],m["meter"],m["cap_exceeded"])')" = "('gpt-stub', 'requested', 1200, 50, None, 'not-reported-tokens-only', 'subscription', 'tokens', False)" ] \
  && ok "codex meta: model requested, 1200 in / 50 out from turn.completed, cost null" || bad "$(cat "$SB/m.json")"
grep -q -- "exec --json - -s read-only --ephemeral --ignore-user-config --ignore-rules --skip-git-repo-check" "$SB/calls" && grep -q -- "--disable shell_tool" "$SB/calls" && grep -q -- "-m gpt-stub" "$SB/calls" \
  && ok "codex call: read-only, ephemeral, user config/rules ignored, shell tool off, -m from registry" || bad "$(cat "$SB/calls")"
[ "$(cat "$SB/stdin")" = "hello from the prompt" ] && ok "codex: prompt on stdin" || bad "stdin"
: > "$SB/calls"; seat gemini_cli
[ "$rc" -eq 0 ] && [ "$(mj '(m["model"],m["model_source"],m["in_tokens"],m["out_tokens"],m["cost_usd"])')" = "('gemini-3-pro', 'cli-reported', 900, 45, None)" ] \
  && ok "gemini meta: model as the CLI reports, in=prompt 900, out=candidates+thoughts 45, cost null" || bad "rc=$rc $(cat "$SB/m.json")"
grep -q -- "-p  -o json --approval-mode plan --skip-trust -e none" "$SB/calls" && ok "gemini call: headless json, plan mode (read-only), extensions off" || bad "$(cat "$SB/calls")"
for k in codex gemini_cli; do mode notok; seat $k
  [ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" != ok ] && [ "$(mj 'm["in_tokens"]')" = None ] && ok "$k: no token report: rc 4 ($(mj 'm["exit"]')), nothing invented" || bad "$k notok rc=$rc"
  mode big; seat $k
  [ "$rc" -eq 0 ] && [ "$(mj 'm["cap_exceeded"]')" = True ] && ok "$k: output overage recorded: $(mj 'm["cap_exceeded_detail"]')" || bad "$k big"
done
mode error; seat codex; [ "$rc" -eq 3 ] && ok "codex error event, no usage: rc 3" || bad "error rc=$rc"

echo "== D (P3) routing: SEAT: codex / gemini_cli / claude_code through the real runner =="
for spec in "codex:codex" "gemini_cli:gemini-cli"; do sid=${spec%%:*}; led=${spec#*:}
  fresh; task 950-$sid "SEAT: $sid" "SCOPE: build"; run
  [ "$rrc" -eq 0 ] && grep -q "^CALL ${led%-cli} " "$SB/calls" && ! grep -q "^CALL claude" "$SB/calls" && ok "SEAT: $sid ran on its adapter ($(tail -1 "$SB/run.out" | cut -c1-80))" || bad "$sid rrc=$rrc $(cat "$SB/run.out")"
  [ "$(lj '[(l["phase"],l["seat"],l["billing"],l["meter"]) for l in L]')" = "[('planned', '$led', 'subscription', 'tokens'), ('actual', '$led', 'subscription', 'tokens')]" ] \
    && ok "$sid: planned + actual lines, subscription/tokens" || bad "$(cat "$FB/ledger.jsonl")"
  [ "$(lj '(L[0]["worst_usd"],L[0]["worst_tokens"],L[1]["cost_usd"],L[1]["cost_source"],L[1]["call_id"]==L[0]["call_id"])')" = "(None, 92000, None, 'not-reported-tokens-only', True)" ] \
    && ok "$sid: no dollar figure anywhere; worst case 92000 tokens; call_ids match" || bad "$sid lines"
  grep -q "scope: build ignored" "$FB/logs/950-$sid.log" && ok "$sid: SCOPE: build widens nothing (logged)" || bad "scope log"
done
fresh; task 951-cc "SEAT: claude_code"; run
[ "$rrc" -eq 0 ] && grep -q "^CALL claude" "$SB/calls" && [ "$(lj 'L[-1]["cost_usd"]')" = 0.25 ] && ok "SEAT: claude_code routes to the Claude seat, dollars as before" || bad "cc rrc=$rrc"
fresh; mode noauth; task 952-noauth "SEAT: codex"; run
[ "$rrc" -eq 4 ] && [ "$(ncall)" -eq 0 ] && [ "$(lj '[l["phase"] for l in L]')" = "['planned']" ] && ok "runner, codex not logged in: no call, no actual line, runner exit 4" || bad "noauth rrc=$rrc $(cat "$FB/ledger.jsonl")"

echo "== E (P3) malformed or unknown SEAT lines refused, no call =="
for bad_line in "SEAT: Codex" "SEAT:codex" "SEAT: codex " "SEAT: codex extra" "SEAT: gemini-cli" "SEAT: nosuch"; do
  fresh; task 953-bad "$bad_line"; run
  [ "$rrc" -eq 5 ] && [ "$(ncall)" -eq 0 ] && [ "$(lj 'L[-1]["phase"]')" = refused ] && [ -e "$FB/held/953-bad.md" ] && ok "refused: '$bad_line'" || bad "'$bad_line' rrc=$rrc"
done
# 027: jev was a CANDIDATE when this was written (task 012). Dan made every seat active on
#  2026-11-01 (jev RATIFIED, task 016), so SEAT: jev is now a recognised api seat. It still
#  makes no call here because the sandbox holds no secrets/jev.key: the refusal must come from
#  the api-seat key check, never from "SEAT line not recognised".
fresh; task 953-jev "SEAT: jev"; run
[ "$rrc" -eq 5 ] && [ "$(ncall)" -eq 0 ] && [ "$(lj '(L[-1]["phase"],L[-1]["seat"],L[-1]["billing"])')" = "('refused', 'jev', 'api')" ] \
  && grep -q 'api seat jev: key file secrets/jev.key missing' "$FB/ledger.jsonl" && ! grep -q 'not recognised' "$FB/ledger.jsonl" \
  && ok "SEAT: jev routes as the active api seat (refused only for the sandbox's missing key)" || bad "jev note $(tail -1 "$FB/ledger.jsonl")"
fresh; task 954-two "SEAT: codex" "SEAT: gemini_cli"; run
[ "$rrc" -eq 5 ] && [ "$(ncall)" -eq 0 ] && ok "two SEAT lines refused" || bad "two"
fresh; echo '{not json' > "$FB/seats/registry.json"; task 955-reg "SEAT: codex"; run
[ "$rrc" -eq 5 ] && [ "$(ncall)" -eq 0 ] && ok "malformed registry: refused, fail closed" || bad "registry rrc=$rrc"

echo "== F (P2) pacing, api class, the two tallies never summed =="
fresh; m=$(date +%Y-%m)
echo "{\"t\":\"$m-01T00:00:00-05:00\",\"round\":\"fx\",\"seat\":\"codex\",\"phase\":\"actual\",\"in_tokens\":1950000,\"out_tokens\":0,\"cost_usd\":null,\"cost_source\":\"not-reported-tokens-only\",\"billing\":\"subscription\",\"meter\":\"tokens\",\"call_id\":\"fx1\"}" > "$FB/ledger.jsonl"
task 956-pace "SEAT: codex"; run
[ "$rrc" -eq 5 ] && [ "$(ncall)" -eq 0 ] && [ "$(lj '(L[-1]["phase"],L[-1]["meter"])')" = "('refused', 'tokens')" ] && ok "codex pacing: 1950000 + 92000 > 2000000 tokens: refused" || bad "pace rrc=$rrc $(tail -1 "$FB/ledger.jsonl")"
task 957-gem "SEAT: gemini_cli"; run
[ "$rrc" -eq 0 ] && ok "gemini pacing is its own tally: codex tokens do not count against it" || bad "gem rrc=$rrc"
echo "{\"t\":\"$m-01T00:00:00-05:00\",\"round\":\"fx\",\"seat\":\"claude-code\",\"phase\":\"actual\",\"cost_usd\":45.0,\"call_id\":\"fx2\"}" >> "$FB/ledger.jsonl"
task 958-cc "SEAT: claude_code"; run
[ "$rrc" -eq 5 ] && [ "$(ncall)" -eq 1 ] && ok "Claude ceiling unaffected by token lines: 45 + 10 > 50 refused" || bad "cc ceiling rrc=$rrc"
# an api seat (registry fixture only; no real api seat exists)
python3 -I - "$FB/seats/registry.json" <<'PY'
import json,sys; p=sys.argv[1]; r=json.load(open(p))
r["seats"]["apifx"]={"ledger_seat":"apifx","adapter":"seats/none.sh","model":"x","billing":"api","meter":"usd","token_class":"frontier","status":"active","card":None}
json.dump(r,open(p,"w"))
PY
task 959-api "SEAT: apifx"; run
[ "$rrc" -eq 5 ] && [ "$(lj '(L[-1]["phase"],L[-1]["billing"])')" = "('refused', 'api')" ] && grep -q "api" "$FB/held/../ledger.jsonl" && ok "api seat refused against api_monthly_ceiling_usd 0.00 (not the subscription ceiling)" || bad "api rrc=$rrc $(tail -1 "$FB/ledger.jsonl")"
n0=$(nled)
echo '{"seat":"apifx","model":"x","finished":"2026-11-01T00:00:00-05:00","in_tokens":5,"out_tokens":5,"cost_usd":null,"cost_source":"not-reported-tokens-only","billing":"api","meter":"tokens"}' > "$FB/logs/api.meta.json"
python3 -I "$FB/bin/budget.py" actual "$FB" fx logs/api.meta.json fx3 1.0 > "$SB/a.out"; arc=$?
[ "$arc" -eq 4 ] && [ "$(nled)" -eq "$n0" ] && ok "api seat reporting no dollars: NOT written, exit 4 ($(cut -c1-70 "$SB/a.out"))" || bad "api actual rc=$arc"
echo '{"seat":"codex","model":"x","finished":"2026-11-01T00:00:00-05:00","in_tokens":5,"out_tokens":5,"cost_usd":1.5,"cost_source":"invented","billing":"subscription","meter":"tokens"}' > "$FB/logs/fab.meta.json"
python3 -I "$FB/bin/budget.py" actual "$FB" fx logs/fab.meta.json fx4 0 > /dev/null; arc=$?
[ "$arc" -eq 4 ] && [ "$(nled)" -eq "$n0" ] && ok "token-seat meta carrying a dollar figure: NOT written" || bad "fab rc=$arc"
python3 -I "$FB/bin/budget.py" summary "$FB" "$m" > "$SB/sum"; src=$?
cat "$SB/sum" | sed 's/^/    | /'
[ "$src" -eq 0 ] && grep -q "subscription.*usd.*45" "$SB/sum" && grep -qE "codex.*1950000" "$SB/sum" && grep -q "api" "$SB/sum" && ok "summary: one line per class, codex tokens and Claude dollars separate" || bad "summary"
! grep -qiE "total|combined|grand" "$SB/sum" && ok "summary prints no combined total" || bad "summary sums"

echo "== G (P2) legacy ledger lines (008-011) still parse =="
fresh; cp "$SRC/ledger.jsonl" "$FB/ledger.jsonl"
python3 -I "$FB/bin/budget.py" summary "$FB" 2026-10 > "$SB/sum"; src=$?
[ "$src" -eq 0 ] && grep -q '25.57' "$SB/sum" && ok "real ledger copy, 2026-10: subscription \$25.57, as before ($(grep -c . "$FB/ledger.jsonl") lines)" || bad "legacy rc=$src $(cat "$SB/sum")"
# 027: the real ledger now also holds api-class lines (api seats live since Dan's 2026-11-01
#  rulings: all seats active, api ceiling $25). Legacy lines (no billing key) must still
#  classify subscription/local; lines that carry a billing key must classify as that key.
python3 -I - "$FB" <<'PY' && ok "every legacy line classifies (no billing key -> subscription, qwen-local -> local); billing-keyed lines keep their class" || bad "line_class"
import json,sys; sys.path.insert(0, sys.argv[1]+"/bin"); import budget
n=0
for l in open(sys.argv[1]+"/ledger.jsonl"):
    if not l.strip(): continue
    j=json.loads(l); c=budget.line_class(j)[0]
    if "billing" in j: assert c==j["billing"], j
    else: assert c in ("subscription","local"), j; n+=1
assert n>0
PY
rm "$FB/seats/registry.json"; task 960-legacy "SEAT: qwen_local"
python3 -I "$FB/bin/budget.py" preflight "$FB" "$FB/queue/960-legacy.md" 960-legacy >/dev/null; prc=$?
[ "$prc" -eq 0 ] && ok "pre-012 tree (no registry.json): Phase 3 seats still route" || bad "legacy registry prc=$prc"

echo "== H (P3) registry, cards, session seats =="
fresh
python3 -I - "$FB" <<'PY' && ok "session.py seats come from the registry: exactly the routable registry seats (jev in since 2026-11-01)" || bad "session seats"
# 027: was "jev out" (jev a CANDIDATE, task 012). Dan made all seats active 2026-11-01.
import json,sys; sys.path.insert(0, sys.argv[1]+"/bin"); import session
reg=json.load(open(sys.argv[1]+"/seats/registry.json"))["seats"]
want={k for k,v in reg.items() if v.get("adapter") and v.get("status") in ("active","awaiting-login")}
assert set(session.SEATS)==want and {"claude_code","qwen_local","codex","gemini_cli","jev","deepseek","perplexity","gemini_api","grok"}==want, session.SEATS
PY
for c in claude_code qwen_local codex gemini_cli jev; do [ -s "$SRC/seats/cards/$c.md" ] || bad "card $c missing"; done
grep -q CANDIDATE "$SRC/seats/cards/jev.md" && ok "five role cards; Jev card marked CANDIDATE" || bad "jev card"

echo "== I live no-auth (real CLIs, no model call: login status / creds check only) =="
fresh; echo "live no-auth probe" > "$SB/p.md"
if command -v codex >/dev/null && ! codex login status >/dev/null 2>&1; then
  fresh; rm -f "$SB/m.json"; t=$(date +%s)
  "${ENV[@]}" HOME="$HOME" "$FB/seats/codex.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
  [ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = no-auth ] && ok "real codex, not logged in: rc 3 no-auth in $(( $(date +%s) - t ))s" || bad "live codex rc=$rc"
else echo "  (skipped: codex absent or logged in)"; fi
if command -v gemini >/dev/null && [ ! -e "$HOME/.gemini/oauth_creds.json" ]; then
  rm -f "$SB/m.json"
  "${ENV[@]}" HOME="$HOME" "$FB/seats/gemini_cli.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
  [ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = no-auth ] && ok "real gemini, not logged in: rc 3 no-auth" || bad "live gemini rc=$rc"
else echo "  (skipped: gemini absent or logged in)"; fi

echo
echo "phase5: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
