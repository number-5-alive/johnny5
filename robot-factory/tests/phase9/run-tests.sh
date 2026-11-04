#!/usr/bin/env bash
# Phase 9 sandbox tests (task 021): the responses-shape core (seats/responses_seat.py)
# behind seats/perplexity.sh. A throwaway fake HOME under tests/phase9/sandbox/,
# the factory's files copied in, a FAKE key in the sandbox secrets/, and
# perplexity's base_url pointed at a loopback fake endpoint (fake_responses.py)
# that replays the REAL task-021 probe replies (fixtures/). No live vendor call,
# no real key, no network beyond loopback. The live tree is only read.
# Usage: run-tests.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HOME/robot-factory"
SB="$HERE/sandbox"; FB="$SB/home/robot-factory"
pass=0; fail=0
ok()  { echo "  PASS: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }
S=perplexity
FAKEKEY="pplx-FAKE-phase9-$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
KEYSHA=$(printf '%s' "$FAKEKEY" | sha256sum | cut -d' ' -f1)
P3TEXT=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["body"]["output"][0]["content"][0]["text"], end="")' "$HERE/fixtures/probe3_ok.json")

rm -rf "$SB"; mkdir -p "$SB"
echo probe2 > "$SB/mode"; : > "$SB/hits"
python3 -I "$HERE/fake_responses.py" "$SB/port" "$SB/mode" "$SB/hits" "$KEYSHA" "$HERE/fixtures" & SRV=$!
trap 'kill $SRV 2>/dev/null; wait $SRV 2>/dev/null' EXIT
for _ in $(seq 50); do [ -s "$SB/port" ] && break; sleep 0.1; done
PORT=$(cat "$SB/port")

reg() {  # reg <python statements on r>: edit the sandbox registry
  python3 -I - "$FB/seats/registry.json" "$1" <<'PY'
import json,sys; p,code=sys.argv[1:]; r=json.load(open(p)); S=r["seats"]; exec(code); json.dump(r,open(p,"w"),indent=1)
PY
}
fresh() {  # sandbox copy of the live tree; perplexity keeps its LIVE prices, only base_url -> loopback
  rm -rf "$FB"; mkdir -p "$FB"/{queue,working,done,logs,work,seats/cards,bin,held,approvals,secrets}
  chmod 700 "$FB/secrets"
  cp "$SRC/run-next.sh" "$SRC/budget.yaml" "$SRC/approve.sh" "$FB/"
  cp "$SRC"/seats/*.sh "$SRC/seats/token_seat.py" "$SRC/seats/api_seat.py" "$SRC/seats/responses_seat.py" "$SRC/seats/registry.json" "$FB/seats/"
  cp "$SRC"/seats/cards/*.md "$FB/seats/cards/"
  cp "$SRC/bin/budget.py" "$SRC/bin/session.py" "$FB/bin/"
  chmod +x "$FB/run-next.sh" "$FB/seats/"*.sh
  : > "$FB/ledger.jsonl"
  sed -i -E 's/^api_monthly_ceiling_usd: .*/api_monthly_ceiling_usd: 5.00/' "$FB/budget.yaml"
  (umask 177; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$S.key")
  reg "S['$S']['api']['base_url']='http://127.0.0.1:$PORT'"
  echo probe2 > "$SB/mode"; cat "$SB/hits" >> "$SB/allhits" 2>/dev/null; : > "$SB/hits"
}
mode() { echo "$1" > "$SB/mode"; }
hits() { wc -l < "$SB/hits"; }
seat() {  # seat [args]: direct adapter call; sets rc
  rm -f "$SB/m.json" "$SB/o.md"
  HOME="$SB/home" "$FB/seats/$S.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" "$@" 2> "$SB/err"; rc=$?
  cat "$SB/err" >> "$SB/allerr"; [ -f "$SB/m.json" ] && cat "$SB/m.json" >> "$SB/allmeta"; [ -f "$SB/o.md" ] && cat "$SB/o.md" >> "$SB/allmeta"; }
mj() { python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); print(eval(sys.argv[2],{"m":m}))' "$SB/m.json" "$1"; }
hj() { tail -1 "$SB/hits" | python3 -I -c 'import json,sys; j=json.loads(sys.stdin.read()); print(eval(sys.argv[1],{"j":j}))' "$1"; }
lastl() { tail -1 "$FB/ledger.jsonl" | python3 -I -c 'import json,sys; j=json.loads(sys.stdin.read()); print(eval(sys.argv[1],{"j":j}))' "$1"; }
# 027: ratified 2026-11-01 perplexity/sonar prices $1.00 in / $2.50 out per Mtok + $0.005 per call (was $1/$1)
cost() { python3 -I -c "print(round($1*1.0/1e6+$2*2.5/1e6+0.005,8))"; }
: > "$SB/allerr"; : > "$SB/allmeta"
printf 'Say hello.\nLine two: caf\xc3\xa9 \xe2\x80\x94 "quoted" {braces}\n' > "$SB/p.md"

echo "== K: key discipline (no call may happen) =="
fresh; rm "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = no-key ] && [ "$(hits)" -eq 0 ] && ok "no key file -> exit 3 no-key, no call" || bad "no key (rc $rc)"
(umask 133; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$S.key"); seat
[ "$rc" -eq 3 ] && grep -q "wider than 600" "$SB/m.json" && [ "$(hits)" -eq 0 ] && ok "mode 644 -> exit 3, no call" || bad "644 (rc $rc)"
chmod 640 "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "mode 640 (group read) -> exit 3, no call" || bad "640 (rc $rc)"
chmod 000 "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "unreadable key file (000) -> exit 3, no call" || bad "000 (rc $rc)"
rm -f "$FB/secrets/$S.key"; (umask 177; printf '%s\n' "$FAKEKEY" > "$SB/elsewhere.key"); ln -s "$SB/elsewhere.key" "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && grep -q "symlink" "$SB/m.json" && [ "$(hits)" -eq 0 ] && ok "symlinked key -> exit 3, no call" || bad "symlink (rc $rc)"
rm -f "$FB/secrets/$S.key"; (umask 177; printf 'two words\n' > "$FB/secrets/$S.key"); seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = no-key ] && [ "$(hits)" -eq 0 ] && ok "malformed key (whitespace) -> exit 3, no call" || bad "malformed (rc $rc)"
rm -f "$FB/secrets/$S.key"; (umask 177; printf 'k\001ey\n' > "$FB/secrets/$S.key"); seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "control char in key -> exit 3, no call" || bad "ctrl key (rc $rc)"
rm -f "$FB/secrets/$S.key"; (umask 177; head -c 5000 /dev/zero | tr '\0' k > "$FB/secrets/$S.key"); seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "oversized key file (>4096 bytes) -> exit 3, no call" || bad "big key (rc $rc)"
rm -f "$FB/secrets/$S.key"
PERPLEXITY_API_KEY="$FAKEKEY" PPLX_API_KEY="$FAKEKEY" OPENAI_API_KEY="$FAKEKEY" seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "key in env vars is ignored: no key file -> exit 3, no call" || bad "env key (rc $rc)"
(umask 177; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$S.key")
reg "S['$S']['api']['price_out_per_mtok_usd']=None"; seat
[ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = unpriced-api ] && [ "$(hits)" -eq 0 ] && ok "null price -> exit 4 unpriced-api, no call" || bad "null price (rc $rc)"
reg "S['$S']['api']['price_out_per_mtok_usd']=1.0; S['$S']['api']['price_per_call_usd']=None"; seat
[ "$rc" -eq 4 ] && [ "$(hits)" -eq 0 ] && ok "null per-call fee -> exit 4 unpriced-api, no call" || bad "null pcall (rc $rc)"
fresh; reg "S['$S']['api']['shape']='openai-chat'"; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = unconfigured ] && [ "$(hits)" -eq 0 ] && ok "registry shape not 'responses' -> exit 3 unconfigured, no call" || bad "shape (rc $rc)"
fresh; reg "S['$S']['model']=None"; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = unconfigured ] && [ "$(hits)" -eq 0 ] && ok "null model -> exit 3 unconfigured" || bad "null model (rc $rc)"
fresh; reg "S['$S']['api']['base_url']='http://example.invalid'"; seat
[ "$rc" -eq 3 ] && grep -q "must be https" "$SB/m.json" && ok "non-loopback http refused before any network" || bad "http (rc $rc)"
fresh; mode redirect; seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 1 ] && grep -q "redirect refused" "$SB/m.json" && ok "redirect refused, the key is not re-sent (1 request)" || bad "redirect (rc $rc, hits $(hits))"

echo "== R: request construction =="
fresh; mode probe2; seat
[ "$(hj 'j["path"],j["method"],j["content_type"]')" = "('/v1/responses', 'POST', 'application/json')" ] && ok "POST /v1/responses, application/json" || bad "path: $(tail -1 "$SB/hits")"
[ "$(hj 'j["auth_match"]')" = True ] && ok "Bearer key from the file reached the endpoint (sha256 match)" || bad "auth"
[ "$(hj 'j["keys"]')" = "['input', 'max_output_tokens', 'model']" ] && ok "body has exactly model, input, max_output_tokens (no messages/tools/stream)" || bad "keys: $(hj 'j["keys"]')"
[ "$(hj 'j["model"]')" = "$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["seats"]["perplexity"]["model"])' "$FB/seats/registry.json")" ] && ok "model is the registry model, verbatim" || bad "model $(hj 'j["model"]')"
[ "$(hj 'j["input_type"],j["input_sha256"]')" = "('str', '$(sha256sum < "$SB/p.md" | cut -d' ' -f1)')" ] && ok "input is the prompt file's exact text (UTF-8, byte-identical)" || bad "input"
[ "$(hj 'j["max_output_tokens"]')" = 8000 ] && ok "max_output_tokens defaults to api.max_out_tokens 8000" || bad "maxout default $(hj 'j["max_output_tokens"]')"
seat --max-out-tokens 100; [ "$(hj 'j["max_output_tokens"]')" = 100 ] && [ "$(mj 'm["max_out_tokens"]')" = 100 ] && ok "--max-out-tokens 100 passed as max_output_tokens" || bad "maxout 100"
n=$(hits); seat --max-out-tokens 9000; [ "$rc" -eq 3 ] && [ "$(hits)" -eq "$n" ] && ok "--max-out-tokens above api.max_out_tokens refused, no call" || bad "maxout 9000 (rc $rc)"
n=$(hits); seat --max-out-tokens 1e3; [ "$rc" -eq 3 ] && [ "$(hits)" -eq "$n" ] && ok "non-integer --max-out-tokens refused, no call" || bad "maxout 1e3 (rc $rc)"
head -c 200000 /dev/zero | tr '\0' a > "$SB/big.md"; rm -f "$SB/m.json"; n=$(hits)
HOME="$SB/home" "$FB/seats/$S.sh" --prompt "$SB/big.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
[ "$rc" -eq 3 ] && [ "$(hits)" -eq "$n" ] && ok "prompt over api.max_in_tokens refused, no call" || bad "big prompt (rc $rc)"
echo x > "$SB/m.json"; n=$(hits); HOME="$SB/home" "$FB/seats/$S.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" 2>/dev/null; rc=$?
[ "$rc" -eq 3 ] && [ "$(cat "$SB/m.json")" = x ] && [ "$(hits)" -eq "$n" ] && ok "existing meta refused, never overwritten, no call" || bad "meta overwrite (rc $rc)"

echo "== X: text extraction (real probe replies) =="
fresh; mode probe2; seat
[ "$rc" -eq 0 ] && [ "$(cat "$SB/o.md")" = Blue ] && [ "$(mj 'm["exit"],m["vendor_status"]')" = "('ok', 'completed')" ] && ok "probe 2 reply -> out is exactly 'Blue', exit 0" || bad "probe2 (rc $rc): $(cat "$SB/o.md")"
[ "$(mj 'm["model"],m["model_source"]')" = "('perplexity/sonar', 'response')" ] && ok "meta model from the response (perplexity/sonar)" || bad "model meta"
[ "$(mj 'm["search"]["present"],m["search"]["annotations"],m["search"]["citations"],m["search"]["search_results"],m["search"]["other_output_items"]')" = "(False, 0, 0, 0, 0)" ] && ok "probe 2: meta.search records no search material (present false, all counts 0)" || bad "probe2 search $(mj 'm["search"]')"
mode probe3; seat
[ "$rc" -eq 0 ] && [ "$(cat "$SB/o.md")" = "$P3TEXT" ] && ok "probe 3 reply -> out is the model's own sentence verbatim (its inline link is its words)" || bad "probe3 text"
[ "$(mj 'm["search"]["present"]')" = False ] && ok "probe 3: no structured citations in the real reply, recorded as none" || bad "probe3 search"
mode cited; seat
[ "$rc" -eq 0 ] && [ "$(cat "$SB/o.md")" = "$P3TEXT" ] && ok "cited (synthetic on probe 3): out is still exactly the model text" || bad "cited text (rc $rc): $(cat "$SB/o.md")"
! grep -qE "synthetic\.example|SYNTH" "$SB/o.md" && ok "cited: no citation URL, title, snippet or search result reaches out" || bad "citation leaked into out"
[ "$(mj 'm["search"]["present"],m["search"]["annotations"],m["search"]["citations"],m["search"]["search_results"],m["search"]["other_output_items"]')" = "(True, 2, 3, 1, 1)" ] \
  && [ "$(mj 'm["search"]["annotation_types"],m["search"]["other_output_types"]')" = "({'url_citation': 2}, {'search_results': 1})" ] \
  && ok "cited: meta.search records presence and counts (2 annotations, 3 citations, 1 search result, 1 non-message item)" || bad "cited meta $(mj 'm["search"]')"
! grep -qE "synthetic\.example|SYNTH" "$SB/m.json" && ok "cited: meta holds counts only, not the citation content" || bad "citation content in meta"

echo "== U: usage mapping and dollars =="
fresh; mode probe2; seat
[ "$(mj 'm["in_tokens"],m["out_tokens"]')" = "(38, 5)" ] && ok "usage input_tokens/output_tokens -> in_tokens/out_tokens (38, 5)" || bad "tokens $(mj 'm["in_tokens"],m["out_tokens"]')"
[ "$(mj 'm["cost_usd"]')" = "$(cost 38 5)" ] && ok "cost_usd \$$(cost 38 5) = 38 x \$1 + 5 x \$2.50 per Mtok + \$0.005 per call (registry prices)" || bad "cost $(mj 'm["cost_usd"]')"
[ "$(mj 'm["price_in_per_mtok_usd"],m["price_out_per_mtok_usd"],m["price_per_call_usd"],m["billing"],m["meter"]')" = "(1.0, 2.5, 0.005, 'api', 'usd')" ] && ok "meta carries the registry prices, billing api, meter usd" || bad "price meta"
[ "$(mj 'm["vendor_reported_cost"]["total_cost"]')" = 2e-05 ] && ok "vendor usage.cost recorded as vendor_reported_cost only (never billed from)" || bad "vendor cost"
[ "$(mj 'm["worst_case_usd"]')" = "$(cost 60000 8000)" ] && ok "worst_case_usd \$$(cost 60000 8000) = 60000 x \$1 + 8000 x \$2.50 per Mtok + \$0.005 per call" || bad "worst $(mj 'm["worst_case_usd"]')"
mode probe3; seat; [ "$(mj 'm["in_tokens"],m["out_tokens"],m["cost_usd"]')" = "(42, 35, $(cost 42 35))" ] && ok "probe 3: (42, 35) -> \$$(cost 42 35)" || bad "probe3 usage"
mode extratotal; seat; [ "$rc" -eq 0 ] && [ "$(mj 'm["out_tokens"],m["cost_usd"]')" = "(1035, $(cost 42 1035))" ] && ok "total_tokens above input+output: the excess is billed as output" || bad "extratotal $(mj 'm["out_tokens"]')"

echo "== F: refusal and failure paths =="
mode nousage; seat
[ "$rc" -eq 4 ] && [ "$(mj 'm["exit"],m["cost_usd"]')" = "('usage-missing', None)" ] && [ "$(cat "$SB/o.md")" = "$P3TEXT" ] && ok "no usage -> exit 4 usage-missing, no cost guessed, text kept" || bad "nousage (rc $rc)"
mode badusage; seat
[ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = usage-missing ] && ok "non-integer usage -> exit 4 usage-missing" || bad "badusage (rc $rc)"
mode garbage; seat
[ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = unparsed ] && [ -f "$SB/o.md" ] && [ ! -s "$SB/o.md" ] && ok "non-JSON reply -> exit 4 unparsed, empty out exists" || bad "garbage (rc $rc)"
mode nomessage; seat
[ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = unparsed ] && ok "no assistant message in output -> exit 4 unparsed" || bad "nomessage (rc $rc)"
mode incomplete; seat
[ "$rc" -eq 2 ] && [ "$(mj 'm["exit"],m["cost_usd"]')" = "('capped', $(cost 42 35))" ] && [ "$(mj 'm["incomplete_details"]["reason"]')" = max_output_tokens ] && ok "status incomplete -> exit 2 capped, cost still recorded" || bad "incomplete (rc $rc)"
mode failed; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"],m["cost_usd"]')" = "('seat-error', $(cost 42 35))" ] && ok "status failed -> exit 3 seat-error, reported usage still costed" || bad "failed (rc $rc)"
mode vendorerr; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = seat-error ] && grep -q "synthetic vendor error" "$SB/m.json" && ok "error object in reply -> exit 3 seat-error" || bad "vendorerr (rc $rc)"
mode probe1; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"],m["cost_usd"]')" = "('http-error', None)" ] && grep -q 'is not supported' "$SB/m.json" && ok "real probe 1 reply (HTTP 400 model not supported) -> exit 3 http-error, vendor words in meta" || bad "probe1 (rc $rc)"
mode error500; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = http-error ] && ok "HTTP 500 -> exit 3 http-error" || bad "500 (rc $rc)"
mode hang; t=$(date +%s); seat --timeout 2; d=$(( $(date +%s) - t ))
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = timeout ] && [ "$d" -le 6 ] && ok "hung endpoint -> exit 3 timeout in ${d}s" || bad "hang (rc $rc, ${d}s)"

echo "== L: budget.py ledger integration (runner) =="
q() { printf 'SEAT: %s\nSCOPE: build\n\nSay hello.\n' "$1" > "$FB/queue/$2.md"; }
run() { HOME="$SB/home" bash "$FB/run-next.sh" > "$SB/run.out" 2>&1; rrc=$?; cat "$SB/run.out" >> "$SB/allerr"; }
# 027: the live perplexity status is 'active' since the 2026-11-01 ruling; the awaiting-adapter
# refusal is still a requirement, so the sandbox fixture now sets that status itself.
fresh; reg "S['$S']['status']='awaiting-adapter'"; q $S t1; run
[ "$rrc" -eq 5 ] && [ "$(lastl 'j["phase"]')" = refused ] && [ "$(hits)" -eq 0 ] && ok "status awaiting-adapter (sandbox fixture): runner refuses, no call" || bad "awaiting-adapter (rrc $rrc)"
fresh; reg "S['$S']['status']='active'"; mode probe2; q $S t2; run
pl=$(grep '"phase": *"planned"' "$FB/ledger.jsonl" | tail -1)
[ "$rrc" -eq 0 ] && [ "$(lastl 'j["phase"],j["billing"],j["meter"],j["cost_usd"],j["in_tokens"],j["out_tokens"],j["price_per_call_usd"]')" = "('actual', 'api', 'usd', $(cost 38 5), 38, 5, 0.005)" ] \
  && ok "runner: actual line \$$(cost 38 5), tokens (38, 5), per-call fee 0.005, billing api" || bad "runner actual (rrc $rrc): $(tail -1 "$FB/ledger.jsonl")"
# 027: worst 0.085 -> 0.09 (2026-11-01 ratified out price); approver/scope keys added to the planned line by task 026b (2026-11-02)
echo "$pl" | grep -q '"worst_usd": *0.09' && [ "$(echo "$pl" | python3 -I -c 'import json,sys; j=json.loads(sys.stdin.read()); print(("approver" in j, j.get("approver"), j.get("scope")))')" = "(True, None, 'build-write')" ] \
  && ok "planned line: worst case \$0.09 (0.085 incl. \$0.005 per call, rounded up); approver null, scope build-write (026b)" || bad "planned: $pl"
[ "$(hj 'j["path"]')" = /v1/responses ] && ok "runner dispatched perplexity through responses_seat.py (/v1/responses)" || bad "runner path"
grep -rqx "Blue" "$FB/logs" "$FB/work" "$FB/done" 2>/dev/null && ok "runner: the answer text lands in the task output" || bad "runner answer"
fresh; reg "S['$S']['status']='active'"; mode probe2; rm "$FB/secrets/$S.key"; q $S t3; run
[ "$rrc" -eq 5 ] && grep -q "key file" "$FB/ledger.jsonl" && [ "$(hits)" -eq 0 ] && ok "runner pre-flight: no key file -> refused, no call" || bad "pf key (rrc $rrc)"
fresh; reg "S['$S']['status']='active'"; mode nousage; q $S t4; run
! grep -q '"phase": *"actual"' "$FB/ledger.jsonl" && ok "runner: usage missing -> no actual line (nothing guessed)" || bad "nousage actual written"
fresh; reg "S['$S']['status']='active'"; q $S t5
pf=$(python3 -I "$FB/bin/budget.py" preflight "$FB" "$FB/queue/t5.md" t5 "$(date -Is)"); read -r _ cid _ worst _ <<< "$pf"
src=$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["seats"]["perplexity"]["api"]["price_source"])' "$FB/seats/registry.json")
mkm() { python3 -I -c 'import json,sys; json.dump({"seat":"perplexity","model":"m","started":"s","finished":"f","in_tokens":38,"out_tokens":5,"cost_usd":float(sys.argv[2]),"price_source":sys.argv[3],"billing":"api","meter":"usd","exit":"ok"},open(sys.argv[1],"x"))' "$@"; }
mkm "$FB/logs/x1.json" 0.000043 "$src"
python3 -I "$FB/bin/budget.py" actual "$FB" t5 logs/x1.json "$cid" "$worst" > /dev/null; arc=$?
[ "$arc" -eq 4 ] && ! grep -q '"actual"' "$FB/ledger.jsonl" && ok "budget.actual: cost without the per-call fee -> exit 4, no line" || bad "actual no-fee ($arc)"
mkm "$FB/logs/x2.json" 2e-05 "$src"
python3 -I "$FB/bin/budget.py" actual "$FB" t5 logs/x2.json "$cid" "$worst" > /dev/null; arc=$?
[ "$arc" -eq 4 ] && ok "budget.actual: vendor-reported cost instead of registry cost -> exit 4" || bad "actual vendor cost ($arc)"
mkm "$FB/logs/x3.json" "$(cost 38 5)" "$src"
python3 -I "$FB/bin/budget.py" actual "$FB" t5 logs/x3.json "$cid" "$worst" > /dev/null; arc=$?
[ "$arc" -eq 0 ] && ok "budget.actual: tokens x registry prices + fee accepted" || bad "actual match ($arc)"

echo "== D: no key material anywhere; loopback only =="
cat "$SB/hits" >> "$SB/allhits"
if grep -rqF -- "$FAKEKEY" "$SB/allmeta" "$SB/allerr" "$FB/ledger.jsonl" "$FB/logs" "$FB/done" "$SB/allhits" 2>/dev/null; then bad "fake key found in output"; else ok "fake key appears in no meta, out, stderr, log, ledger or fake-server record"; fi
grep -q '"auth_match": true' "$SB/allhits" && ! grep -q "pplx-" "$SB/allhits" && ok "fake server records only a sha256 match flag" || bad "hits file"
[ "$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["seats"]["perplexity"]["api"]["base_url"])' "$FB/seats/registry.json")" = "http://127.0.0.1:$PORT" ] && ok "sandbox perplexity base_url is loopback" || bad "sandbox base_url"

echo "== P: the live tree =="
python3 -I - "$SRC/seats/registry.json" "$SRC/seats/registry.json.bak-pre-021-20261101" <<'PY' && ok "live registry perplexity entry vs pre-021: api.shape -> responses, appended facts_status/price_source; 2026-11-01 ruling: status active, model perplexity/sonar, out price 2.50; nothing else" || bad "live registry diff"
import json,sys
new,old=(json.load(open(p)) for p in sys.argv[1:3])
a,b=new["seats"]["perplexity"],old["seats"]["perplexity"]
assert a["api"]["shape"]=="responses" and b["api"]["shape"]=="openai-chat"
assert a["api"]["facts_status"].startswith(b["api"]["facts_status"]) and len(a["api"]["facts_status"])>len(b["api"]["facts_status"])
assert a["api"]["price_source"].startswith(b["api"]["price_source"])  # 027: ratification note appended
for x in (a,b): x["api"].pop("shape"); x["api"].pop("facts_status"); x["api"].pop("price_source")
# 027: the 2026-11-01 ruling (all seats active; perplexity is perplexity/sonar at $1.00/$2.50 + $0.005/call)
assert (b.pop("status"),a.pop("status"))==("awaiting-adapter","active")
assert (b.pop("model"),a.pop("model"))==("sonar","perplexity/sonar")
assert (b["api"].pop("price_out_per_mtok_usd"),a["api"].pop("price_out_per_mtok_usd"))==(1.0,2.5)
assert a==b
assert (a["api"]["price_in_per_mtok_usd"],a["api"]["price_per_call_usd"],a["api"]["price_status"])==(1.0,0.005,"RATIFIED")
PY
grep -q 'responses_seat.py" perplexity' "$SRC/seats/perplexity.sh" && ! grep -q 'api_seat.py" perplexity' "$SRC/seats/perplexity.sh" && ok "perplexity.sh execs responses_seat.py" || bad "wrapper"
! grep -l responses_seat "$SRC"/seats/{jev,deepseek,gemini_api,grok}.sh >/dev/null 2>&1 && grep -q 'api_seat.py" deepseek' "$SRC/seats/deepseek.sh" && ok "other api wrappers still exec api_seat.py" || bad "other wrappers"

echo
echo "phase9: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
