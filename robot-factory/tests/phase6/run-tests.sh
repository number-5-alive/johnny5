#!/usr/bin/env bash
# Phase 6 sandbox tests (task 014): the api seats. A throwaway fake HOME under
# tests/phase6/sandbox/, the factory's files copied in, FAKE keys in the
# sandbox secrets/, and every seat's base_url pointed at a loopback fake
# endpoint (fake_api.py, 127.0.0.1). No live vendor call, no real key, no
# network beyond loopback. The live tree is only read (ceiling, ledger, statuses).
# Usage: run-tests.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HOME/robot-factory"
SB="$HERE/sandbox"; FB="$SB/home/robot-factory"
pass=0; fail=0
ok()  { echo "  PASS: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }
SEATS="deepseek gemini_api grok"   # jev moved to tests/phase8 (task 016b: SystemOne shape); perplexity moved to tests/phase9 (task 021: responses shape)
FAKEKEY="sk-FAKE-phase6-$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
KEYSHA=$(printf '%s' "$FAKEKEY" | sha256sum | cut -d' ' -f1)

rm -rf "$SB"; mkdir -p "$SB"
LIVESUM=$(cd "$SRC" && sha256sum budget.yaml ledger.jsonl seats/registry.json)
echo ok > "$SB/mode"; : > "$SB/hits"
python3 -I "$HERE/fake_api.py" "$SB/port" "$SB/mode" "$SB/hits" "$KEYSHA" & SRV=$!
trap 'kill $SRV 2>/dev/null; wait $SRV 2>/dev/null' EXIT
for _ in $(seq 50); do [ -s "$SB/port" ] && break; sleep 0.1; done
PORT=$(cat "$SB/port")

reg() {  # reg <python statements on r>: edit the sandbox registry
  python3 -I - "$FB/seats/registry.json" "$1" <<'PY'
import json,sys; p,code=sys.argv[1:]; r=json.load(open(p)); S=r["seats"]; exec(code); json.dump(r,open(p,"w"),indent=1)
PY
}
fresh() {
  rm -rf "$FB"; mkdir -p "$FB"/{queue,working,done,logs,work,seats/cards,bin,held,approvals,secrets}
  chmod 700 "$FB/secrets"
  cp "$SRC/run-next.sh" "$SRC/budget.yaml" "$SRC/approve.sh" "$FB/"
  cp "$SRC"/seats/*.sh "$SRC/seats/token_seat.py" "$SRC/seats/api_seat.py" "$SRC/seats/registry.json" "$FB/seats/"
  cp "$SRC"/seats/cards/*.md "$FB/seats/cards/"
  cp "$SRC/bin/budget.py" "$SRC/bin/session.py" "$FB/bin/"
  chmod +x "$FB/run-next.sh" "$FB/seats/"*.sh
  : > "$FB/ledger.jsonl"
  # 027: the live ceiling is now 25.00 (Dan, 2026-11-01 13:23 CT); the old literal 0.00 match was a
  # silent no-op. Set the sandbox fixture value 5.00 whatever the live value is.
  sed -i 's/^api_monthly_ceiling_usd: .*/api_monthly_ceiling_usd: 5.00/' "$FB/budget.yaml"
  for s in $SEATS; do (umask 177; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$s.key"); done
  reg "
for s in '$SEATS'.split():
    a=S[s]['api']; a.update(base_url='http://127.0.0.1:$PORT', shape='openai-chat',
        price_in_per_mtok_usd=1.0, price_out_per_mtok_usd=2.0, price_source='TEST FIXTURE (not a vendor price)')
    if S[s]['model'] is None: S[s]['model']='fixture-'+s
# 027: seats not exercised here (jev, perplexity) carry real vendor base_urls since their
# ratification (2026-11-01); point them at loopback too so the sandbox holds zero vendor hosts.
for s,e in S.items():
    if isinstance(e.get('api'),dict) and e['api'].get('base_url'): e['api']['base_url']='http://127.0.0.1:$PORT'
"
  echo ok > "$SB/mode"; cat "$SB/hits" >> "$SB/allhits" 2>/dev/null; : > "$SB/hits"
}
mode() { echo "$1" > "$SB/mode"; }
hits() { wc -l < "$SB/hits"; }
seat() {  # seat <id> [args]: direct adapter call; sets rc
  local k=$1; shift; echo "hello from the prompt" > "$SB/p.md"; rm -f "$SB/m.json" "$SB/o.md"
  HOME="$SB/home" "$FB/seats/$k.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" "$@" 2> "$SB/err"; rc=$?
  cat "$SB/err" >> "$SB/allerr"; [ -f "$SB/m.json" ] && cat "$SB/m.json" >> "$SB/allmeta"; [ -f "$SB/o.md" ] && cat "$SB/o.md" >> "$SB/allmeta"; }
mj() { python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); print(eval(sys.argv[2],{"m":m}))' "$SB/m.json" "$1"; }
lastl() { tail -1 "$FB/ledger.jsonl" | python3 -I -c 'import json,sys; j=json.loads(sys.stdin.read()); print(eval(sys.argv[1],{"j":j}))' "$1"; }
: > "$SB/allerr"; : > "$SB/allmeta"

echo "== D1/D2/D3: each wrapper, against the fake endpoint =="
for s in $SEATS; do
  fresh; pc=0
  rm "$FB/secrets/$s.key"; seat "$s"
  [ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = no-key ] && [ "$(hits)" -eq 0 ] && ok "$s: no key file -> exit 3 no-key, no call" || bad "$s: no key (rc $rc)"
  (umask 133; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$s.key"); seat "$s"
  [ "$rc" -eq 3 ] && grep -q "wider than 600" "$SB/m.json" && [ "$(hits)" -eq 0 ] && ok "$s: mode 644 -> exit 3, no call" || bad "$s: wide perms (rc $rc)"
  chmod 640 "$FB/secrets/$s.key"; seat "$s"
  [ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "$s: mode 640 (group read) -> exit 3" || bad "$s: 640 (rc $rc)"
  chmod 000 "$FB/secrets/$s.key"; seat "$s"
  [ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "$s: unreadable key file (000) -> exit 3" || bad "$s: unreadable (rc $rc)"
  rm -f "$FB/secrets/$s.key"; (umask 177; printf '%s\n' "$FAKEKEY" > "$SB/elsewhere.key"); ln -s "$SB/elsewhere.key" "$FB/secrets/$s.key"; seat "$s"
  [ "$rc" -eq 3 ] && grep -q "symlink" "$SB/m.json" && [ "$(hits)" -eq 0 ] && ok "$s: symlinked key -> exit 3" || bad "$s: symlink (rc $rc)"
  rm -f "$FB/secrets/$s.key"; (umask 177; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$s.key")
  reg "S['$s']['api']['price_out_per_mtok_usd']=None"; seat "$s"
  [ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = unpriced-api ] && [ "$(hits)" -eq 0 ] && ok "$s: null price -> exit 4 unpriced-api, no call" || bad "$s: null price (rc $rc)"
  reg "S['$s']['api']['price_out_per_mtok_usd']=2.0"
  seat "$s"
  want=$(python3 -c "print(round(1234*1.0/1e6+567*2.0/1e6+$pc,8))")
  [ "$rc" -eq 0 ] && [ "$(mj 'm["cost_usd"]')" = "$want" ] && [ "$(mj 'm["in_tokens"],m["out_tokens"]')" = "(1234, 567)" ] \
    && [ "$(mj 'm["billing"],m["meter"],m["price_source"]')" = "('api', 'usd', 'TEST FIXTURE (not a vendor price)')" ] \
    && [ "$(cat "$SB/o.md")" = "fake reply text" ] && ok "$s: priced success, cost \$$want = 1234 x \$1 + 567 x \$2 per Mtok + \$$pc" || bad "$s: priced success (rc $rc, cost $(mj 'm.get("cost_usd")'))"
  tail -1 "$SB/hits" | grep -q '"auth_match": true' && tail -1 "$SB/hits" | grep -q '"path": "/chat/completions"' \
    && ok "$s: bearer key from the file reached the endpoint (sha256 match), path /chat/completions" || bad "$s: auth/path"
  mode nousage; seat "$s"
  [ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = usage-missing ] && [ "$(mj 'm["cost_usd"]')" = None ] && ok "$s: no usage reported -> exit 4, no cost guessed" || bad "$s: nousage (rc $rc)"
  mode length; seat "$s"
  [ "$rc" -eq 2 ] && [ "$(mj 'm["exit"]')" = capped ] && [ "$(mj 'm["cost_usd"]')" = "$want" ] && ok "$s: finish_reason length -> exit 2 capped, cost still recorded" || bad "$s: length (rc $rc)"
done

echo "== core edge cases (deepseek) =="
fresh
mode error500; seat deepseek; [ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = http-error ] && ok "HTTP 500 -> exit 3" || bad "500 (rc $rc)"
mode garbage;  seat deepseek; [ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = unparsed ] && ok "non-JSON reply -> exit 4 unparsed" || bad "garbage (rc $rc)"
mode redirect; : > "$SB/hits"; seat deepseek
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 1 ] && grep -q "redirect refused" "$SB/m.json" && ok "redirect refused, the key is not re-sent (1 request)" || bad "redirect (rc $rc, hits $(hits))"
mode hang; t=$(date +%s); seat deepseek --timeout 2; d=$(( $(date +%s) - t ))
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = timeout ] && [ "$d" -le 6 ] && ok "hung endpoint -> exit 3 timeout in ${d}s" || bad "hang (rc $rc, ${d}s)"
mode reasoning; seat deepseek
[ "$rc" -eq 0 ] && [ "$(mj 'm["out_tokens"]')" = 1567 ] && ok "reasoning tokens (total > prompt+completion) billed as output" || bad "reasoning (rc $rc)"
mode ok; echo x > "$SB/m.json"; HOME="$SB/home" "$FB/seats/deepseek.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
[ "$rc" -eq 3 ] && [ "$(cat "$SB/m.json")" = x ] && ok "existing meta refused, never overwritten" || bad "meta overwrite (rc $rc)"
rm "$FB/secrets/deepseek.key"; : > "$SB/hits"
echo "hello" > "$SB/p.md"; rm -f "$SB/m.json"
DEEPSEEK_API_KEY="$FAKEKEY" OPENAI_API_KEY="$FAKEKEY" HOME="$SB/home" "$FB/seats/deepseek.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "key in env vars is ignored: no key file -> exit 3, no call" || bad "env key (rc $rc)"
(umask 177; printf '%s\n' "$FAKEKEY" > "$FB/secrets/deepseek.key")
(umask 177; printf 'two words\n' > "$FB/secrets/grok.key"); seat grok
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "malformed key (whitespace) -> exit 3, no call" || bad "malformed key (rc $rc)"
reg "S['grok']['model']=None"; (umask 177; printf '%s\n' "$FAKEKEY" > "$FB/secrets/grok.key"); seat grok
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = unconfigured ] && ok "null model -> exit 3 unconfigured" || bad "unconfigured (rc $rc)"
reg "S['grok']['model']='x'; S['grok']['api']['base_url']='http://example.invalid/v1'"; seat grok
[ "$rc" -eq 3 ] && grep -q "must be https" "$SB/m.json" && ok "non-loopback http refused before any network" || bad "http (rc $rc)"
seat deepseek --max-out-tokens 9000; [ "$rc" -eq 3 ] && ok "--max-out-tokens above api.max_out_tokens refused" || bad "maxout (rc $rc)"
seat deepseek --max-out-tokens 100; tail -1 "$SB/hits" | grep -q '"max_tokens": 100' && ok "--max-out-tokens passed as max_tokens" || bad "max_tokens"
head -c 200000 /dev/zero | tr '\0' a > "$SB/big.md"; rm -f "$SB/m.json"; n=$(hits)
HOME="$SB/home" "$FB/seats/deepseek.sh" --prompt "$SB/big.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
[ "$rc" -eq 3 ] && [ "$(hits)" -eq "$n" ] && ok "prompt over api.max_in_tokens refused, no call" || bad "big prompt (rc $rc)"

echo "== D5: pre-flight and the runner =="
q() { printf 'SEAT: %s\nSCOPE: build\n\nSay hello.\n' "$1" > "$FB/queue/$2.md"; }
run() { HOME="$SB/home" bash "$FB/run-next.sh" > "$SB/run.out" 2>&1; rrc=$?; cat "$SB/run.out" >> "$SB/allerr"; }
# 027: deepseek is active in the live registry (all seats active, Dan 2026-11-01); the
# awaiting-key refusal path is exercised by setting that status in the sandbox fixture.
fresh; reg "S['deepseek']['status']='awaiting-key'"; q deepseek t1; : > "$SB/hits"; run
[ "$rrc" -eq 5 ] && [ "$(lastl 'j["phase"]')" = refused ] && grep -q CANDIDATE "$FB/ledger.jsonl" && [ "$(hits)" -eq 0 ] \
  && ok "status awaiting-key: refused, ledger says CANDIDATE, no call" || bad "awaiting-key (rrc $rrc)"
fresh; reg "S['deepseek']['status']='active'"; sed -i 's/^api_monthly_ceiling_usd: 5.00/api_monthly_ceiling_usd: 0.00/' "$FB/budget.yaml"
q deepseek t2; run
[ "$rrc" -eq 5 ] && [ "$(lastl 'j["phase"],j["billing"]')" = "('refused', 'api')" ] && [ "$(hits)" -eq 0 ] && ok "ceiling 0.00 (the pre-2026-11-01 live value): refused, no call" || bad "ceiling 0 (rrc $rrc)"
fresh; reg "S['deepseek']['status']='active'"; rm "$FB/secrets/deepseek.key"; q deepseek t3; run
[ "$rrc" -eq 5 ] && grep -q "key file" "$FB/ledger.jsonl" && [ "$(lastl 'j["billing"],j["meter"]')" = "('api', 'usd')" ] && ok "pre-flight 1: no key file -> refused (billing api)" || bad "pf key (rrc $rrc)"
fresh; reg "S['deepseek']['status']='active'; S['deepseek']['api']['price_in_per_mtok_usd']=None"; q deepseek t4; run
[ "$rrc" -eq 5 ] && grep -q "unpriced-api" "$FB/ledger.jsonl" && [ "$(hits)" -eq 0 ] && ok "pre-flight 2: null price -> refused" || bad "pf price (rrc $rrc)"
fresh; reg "S['deepseek']['status']='active'"; chmod 644 "$FB/secrets/deepseek.key"; rm "$FB/secrets/deepseek.key"; q deepseek t4b
reg "S['deepseek']['api']['price_in_per_mtok_usd']=None"; run
grep -q "key file" "$FB/ledger.jsonl" && ! grep -q "unpriced" "$FB/ledger.jsonl" && ok "pre-flight order: key file checked before prices" || bad "pf order"
fresh; reg "S['deepseek']['status']='active'; S['deepseek']['api']['price_in_per_mtok_usd']=200.0"; q deepseek t5; run
[ "$rrc" -eq 5 ] && grep -q "api worst case \$12.02" "$FB/ledger.jsonl" && ok "pre-flight 3: worst case \$12.02 (60000 x \$200 + 8000 x \$2) > cap \$10 refused" || bad "pf worst (rrc $rrc)"
fresh; reg "S['deepseek']['status']='active'"; q deepseek t6; run
pl=$(grep '"phase": *"planned"' "$FB/ledger.jsonl" | tail -1)
[ "$rrc" -eq 0 ] && [ "$(lastl 'j["phase"],j["billing"],j["meter"],j["cost_usd"],j["in_tokens"],j["out_tokens"],j["price_source"]')" = "('actual', 'api', 'usd', 0.002368, 1234, 567, 'TEST FIXTURE (not a vendor price)')" ] \
  && ok "runner: actual line carries billing api, meter usd, cost_usd, tokens, price_source" || bad "runner actual (rrc $rrc): $(tail -1 "$FB/ledger.jsonl")"
echo "$pl" | grep -q '"worst_usd": *0.08' && echo "$pl" | grep -q '"price_source"' && ok "planned line: worst case \$0.08 (0.076 rounded up), price_source" || bad "planned: $pl"
grep -q "seat: deepseek (seats/deepseek.sh, api, real dollars" "$FB/logs/t6.log" && grep -q "scope: build ignored" "$FB/logs/t6.log" && ok "log names the api seat; SCOPE: build widens nothing" || bad "log"
m=$(date +%Y-%m); python3 -I "$FB/bin/budget.py" summary "$FB" "$m" > "$SB/sum"
grep -q "api usd (real dollars): actual \$0.00" "$SB/sum" && grep -q "api usd seat deepseek (active): actual \$0.00" "$SB/sum" \
  && ! grep -qiE "total|combined|grand" "$SB/sum" && ok "summary: api tally and per-seat lines, no combined total" || { bad "summary"; cat "$SB/sum"; }
# actual refuses a cost that is not tokens x registry prices
fresh; reg "S['deepseek']['status']='active'"; q deepseek t8
pf=$(python3 -I "$FB/bin/budget.py" preflight "$FB" "$FB/queue/t8.md" t8 "$(date -Is)"); read -r _ cid _ worst _ <<< "$pf"
mkm() { python3 -I -c 'import json,sys; json.dump({"seat":"deepseek","model":"m","started":"s","finished":"f","in_tokens":1234,"out_tokens":567,"cost_usd":float(sys.argv[2]),"price_source":sys.argv[3],"billing":"api","meter":"usd","exit":"ok"},open(sys.argv[1],"x"))' "$@"; }
mkm "$FB/logs/x1.json" 0.0001 "TEST FIXTURE (not a vendor price)"
python3 -I "$FB/bin/budget.py" actual "$FB" t8 logs/x1.json "$cid" "$worst" > /dev/null; arc=$?
[ "$arc" -eq 4 ] && ! grep -q '"actual"' "$FB/ledger.jsonl" && ok "actual: cost_usd not matching tokens x prices -> exit 4, no line" || bad "actual mismatch ($arc)"
mkm "$FB/logs/x2.json" 0.002368 "guessed"
python3 -I "$FB/bin/budget.py" actual "$FB" t8 logs/x2.json "$cid" "$worst" > /dev/null; arc=$?
[ "$arc" -eq 4 ] && ok "actual: wrong price_source -> exit 4" || bad "actual source ($arc)"
mkm "$FB/logs/x3.json" 0.002368 "TEST FIXTURE (not a vendor price)"
python3 -I "$FB/bin/budget.py" actual "$FB" t8 logs/x3.json "$cid" "$worst" > /dev/null; arc=$?
[ "$arc" -eq 0 ] && ok "actual: matching cost accepted" || bad "actual match ($arc)"

echo "== D6: no key material anywhere; no vendor network =="
cat "$SB/hits" >> "$SB/allhits"
if grep -rqF -- "$FAKEKEY" "$SB/allmeta" "$SB/allerr" "$FB/ledger.jsonl" "$FB/logs" "$SB/allhits" 2>/dev/null; then bad "fake key found in output"; else ok "fake key appears in no meta, out, stderr, log, ledger or fake-server record"; fi
grep -q '"auth_match": true' "$SB/allhits" && ! grep -q "sk-" "$SB/allhits" && ok "fake server records only a sha256 match flag" || bad "hits file"
# 027: since ratification (2026-11-01) the registry's facts_status prose quotes vendor URLs, so a
# grep of every URL in the file no longer measures base_urls. Check every *url* field instead.
python3 -I -c '
import json,sys,re
def walk(o):
    if isinstance(o,dict):
        for k,v in o.items():
            if "url" in k.lower() and v is not None: yield v
            yield from walk(v)
    elif isinstance(o,list):
        for v in o: yield from walk(v)
u=list(walk(json.load(open(sys.argv[1]))))
assert len(u)>=5 and all(re.match(r"https?://(127\.0\.0\.1|example\.invalid)[:/]",x) for x in u), u' "$FB/seats/registry.json" \
  && ok "every sandbox base_url is loopback (zero vendor hosts)" || bad "a sandbox base_url points off loopback"

echo "== P2/P3: the live tree is untouched =="
LIVESUM_END=$(cd "$SRC" && sha256sum budget.yaml ledger.jsonl seats/registry.json)
[ "$LIVESUM_END" = "$LIVESUM" ] && ok "live budget.yaml, ledger.jsonl, registry.json byte-identical before and after this suite" || bad "live tree changed during the suite"
# 027: the live ceiling is 25.00 (Dan, 2026-11-01 13:23 CT; the \$50 monthly ceiling stands, classes never summed)
grep -qx "api_monthly_ceiling_usd: 25.00" "$SRC/budget.yaml" && grep -qx "monthly_ceiling_usd: 50.00" "$SRC/budget.yaml" && ok "live api_monthly_ceiling_usd is 25.00, monthly_ceiling_usd 50.00" || bad "live ceiling"
# 027: api seats went live 2026-11-01 (smokes 017-023), so api actual lines now exist; each must be
# a known api seat, meter usd, with a real cost_usd figure.
python3 -I -c '
import json,sys; n=0
for l in open(sys.argv[1]):
    j=json.loads(l)
    if j.get("phase")=="actual" and j.get("billing")=="api":
        n+=1; assert j["seat"] in {"jev","deepseek","perplexity","gemini-api","grok"} and j.get("meter")=="usd" and isinstance(j.get("cost_usd"),(int,float)) and j["cost_usd"]>0, j
assert n>=1' "$SRC/ledger.jsonl" && ok "live ledger: every api actual line is an api seat, meter usd, real cost_usd" || bad "live api actual"
# 027: all seats active and prices RATIFIED (Dan, 2026-11-01); perplexity is perplexity/sonar on the
# responses shape (task 021) at \$1.00/\$2.50 + \$0.005 per call; jev \$0.042/\$0.00.
python3 -I -c '
import json,sys; r=json.load(open(sys.argv[1]))["seats"]
want={"jev":(0.042,0.0,None),"deepseek":(0.28,0.42,None),"perplexity":(1.0,2.5,0.005),"gemini_api":(0.75,3.75,None),"grok":(2.0,6.0,None)}
for s,(i,o,c) in want.items():
    a=r[s]["api"]; assert r[s]["status"]=="active" and a["price_status"]=="RATIFIED" and a["key_file"]=="secrets/%s.key"%s, s
    assert (a["price_in_per_mtok_usd"],a["price_out_per_mtok_usd"],a.get("price_per_call_usd"))==(i,o,c), (s,a)
assert r["perplexity"]["model"]=="perplexity/sonar" and r["perplexity"]["api"]["shape"]=="responses"' "$SRC/seats/registry.json" \
  && ok "live registry: all 5 api seats active, prices RATIFIED at the commissioned values" || bad "live registry"
for s in $SEATS; do grep -q "secrets/$s.key" "$SRC/seats/cards/$s.md" && grep -q "CANDIDATE" "$SRC/seats/cards/$s.md" && grep -q UNVERIFIED "$SRC/seats/cards/$s.md" || { bad "card $s"; continue; }; done && ok "cards: key path, CANDIDATE prices, UNVERIFIED facts"
grep -q "never grants the verified stamp" "$SRC/seats/cards/jev.md" && ok "jev card: never grants the verified stamp" || bad "jev card"

echo
echo "phase6: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
