#!/usr/bin/env bash
# Phase 8 sandbox tests (task 016b; 016c: fractional Score + raw-reply preservation; 016d: legend normalization vs the REAL 019b reply): the TypeSafe SystemOne core (seats/jev_systemone.py)
# behind seats/jev.sh, the Jev templates + bin/jev_ask.py, and the MODERATOR'S RULE
# branch in bin/budget.py. A throwaway fake HOME under tests/phase8/sandbox/, the
# factory's files copied in, a FAKE key in the sandbox secrets/, and jev's base_url
# pointed at a loopback fake endpoint (fake_systemone.py) that replays the REAL
# task-016 probe replies (fixtures/) plus DOCUMENTED-synthetic choice/score answers.
# No live vendor call, no real key, no network beyond loopback. The live tree is only read.
# Usage: run-tests.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HOME/robot-factory"
SB="$HERE/sandbox"; FB="$SB/home/robot-factory"
pass=0; fail=0
ok()  { echo "  PASS: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }
S=jev
FAKEKEY="ts-FAKE-phase8-$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
KEYSHA=$(printf '%s' "$FAKEKEY" | sha256sum | cut -d' ' -f1)
UNREP=unreported-billed-at-worst-case

rm -rf "$SB"; mkdir -p "$SB"
echo auto > "$SB/mode"; : > "$SB/hits"
python3 -I "$HERE/fake_systemone.py" "$SB/port" "$SB/mode" "$SB/hits" "$KEYSHA" "$HERE/fixtures" & SRV=$!
trap 'kill $SRV 2>/dev/null; wait $SRV 2>/dev/null' EXIT
for _ in $(seq 50); do [ -s "$SB/port" ] && break; sleep 0.1; done
PORT=$(cat "$SB/port")

reg() {
  python3 -I - "$FB/seats/registry.json" "$1" <<'PY'
import json,sys; p,code=sys.argv[1:]; r=json.load(open(p)); S=r["seats"]; exec(code); json.dump(r,open(p,"w"),indent=1)
PY
}
fresh() {  # sandbox copy of the live tree; jev keeps its LIVE prices and status, only base_url -> loopback
  rm -rf "$FB"; mkdir -p "$FB"/{queue,working,done,logs,work,seats/cards,bin,held,approvals,secrets}
  chmod 700 "$FB/secrets"
  cp "$SRC/run-next.sh" "$SRC/budget.yaml" "$SRC/approve.sh" "$FB/"
  cp "$SRC"/seats/*.sh "$SRC"/seats/*.py "$SRC/seats/registry.json" "$FB/seats/"
  cp "$SRC"/seats/cards/*.md "$FB/seats/cards/"
  cp "$SRC/bin/budget.py" "$SRC/bin/session.py" "$FB/bin/"
  chmod +x "$FB/run-next.sh" "$FB/seats/"*.sh
  : > "$FB/ledger.jsonl"
  sed -i -E 's/^api_monthly_ceiling_usd: .*/api_monthly_ceiling_usd: 5.00/' "$FB/budget.yaml"
  (umask 177; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$S.key")
  reg "S['$S']['api']['base_url']='http://127.0.0.1:$PORT'"
  echo auto > "$SB/mode"; cat "$SB/hits" >> "$SB/allhits" 2>/dev/null; : > "$SB/hits"
}
mode() { echo "$1" > "$SB/mode"; }
hits() { wc -l < "$SB/hits"; }
seat() {
  rm -f "$SB/m.json" "$SB/o.md"
  HOME="$SB/home" "$FB/seats/$S.sh" --prompt "$SB/p.md" --out "$SB/o.md" --meta "$SB/m.json" "$@" 2> "$SB/err"; rc=$?
  cat "$SB/err" >> "$SB/allerr"; [ -f "$SB/m.json" ] && cat "$SB/m.json" >> "$SB/allmeta"; [ -f "$SB/o.md" ] && cat "$SB/o.md" >> "$SB/allmeta"; }
mj() { python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); print(eval(sys.argv[2],{"m":m}))' "$SB/m.json" "$1"; }
hj() { tail -1 "$SB/hits" | python3 -I -c 'import json,sys; j=json.loads(sys.stdin.read()); print(eval(sys.argv[1],{"j":j}))' "$1"; }
lastl() { tail -1 "$FB/ledger.jsonl" | python3 -I -c 'import json,sys; j=json.loads(sys.stdin.read()); print(eval(sys.argv[1],{"j":j}))' "$1"; }
: > "$SB/allerr"; : > "$SB/allmeta"
P3='JEV-STATE:
On a clear day the sky appears blue.

JEV-QUESTIONS:
- Noul: On a clear day the sky appears blue.'
MIX='JEV-STATE:
The build log shows failing tests, all in parser.py. Café "quoted" {braces} — ok.

JEV-QUESTIONS:
- Noul: The failures are confined to parser.py.
- Choice: Which component most likely broke? | parser | lexer | runner
- Score: Severity of the regression | none | minor | moderate | major | critical'
pm() { printf '%s\n' "$1" > "$SB/p.md"; }
pm "$MIX"

echo "== K: key discipline (no call may happen) =="
fresh; rm "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = no-key ] && [ "$(hits)" -eq 0 ] && ok "no key file -> exit 3 no-key, no call" || bad "no key (rc $rc)"
(umask 133; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$S.key"); seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "mode 644 -> exit 3, no call" || bad "644 (rc $rc)"
chmod 640 "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "mode 640 (group read) -> exit 3, no call" || bad "640 (rc $rc)"
chmod 000 "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "unreadable key file (000) -> exit 3, no call" || bad "000 (rc $rc)"
rm -f "$FB/secrets/$S.key"; (umask 177; printf '%s\n' "$FAKEKEY" > "$SB/elsewhere.key"); ln -s "$SB/elsewhere.key" "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && grep -q "symlink" "$SB/m.json" && [ "$(hits)" -eq 0 ] && ok "symlinked key -> exit 3, no call" || bad "symlink (rc $rc)"
rm -f "$FB/secrets/$S.key"; mkdir -m 700 "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "key path is a directory (not a regular file) -> exit 3, no call" || bad "dir key (rc $rc)"
rmdir "$FB/secrets/$S.key"; (umask 177; printf 'two words\n' > "$FB/secrets/$S.key"); seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "malformed key (whitespace) -> exit 3, no call" || bad "malformed (rc $rc)"
rm -f "$FB/secrets/$S.key"; (umask 177; printf 'k\001ey\n' > "$FB/secrets/$S.key"); seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "control char in key -> exit 3, no call" || bad "ctrl key (rc $rc)"
rm -f "$FB/secrets/$S.key"
TYPESAFE_API_KEY="$FAKEKEY" JEV_API_KEY="$FAKEKEY" SYSTEMONE_API_KEY="$FAKEKEY" seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "key in env vars is ignored: no key file -> exit 3, no call" || bad "env key (rc $rc)"
(umask 177; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$S.key")
reg "S['$S']['api']['base_url']='http://api.example.invalid/v1/systemone'"; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = unconfigured ] && grep -q "must be https" "$SB/m.json" && [ "$(hits)" -eq 0 ] && ok "non-loopback http base_url -> exit 3 unconfigured, no call" || bad "http (rc $rc)"
echo "  (not testable unprivileged: a key file owned by another user; the uid check is in the same fstat test)"

echo "== J: JEV block parsing (malformed -> exit 3 malformed, no call) =="
fresh
jbad() {  # jbad <label> <grep> <block>
  pm "$3"; seat
  [ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = malformed ] && grep -qF -- "$2" "$SB/m.json" && [ "$(hits)" -eq 0 ] && [ -f "$SB/o.md" ] \
    && ok "$1 -> exit 3 malformed, no call" || bad "$1 (rc $rc): $(mj 'm.get("error")' 2>/dev/null)"; }
jbad "no JEV block at all" "need exactly one 'JEV-STATE:' line" 'Just say hello.'
jbad "no JEV-STATE (questions only)" "need exactly one" $'JEV-QUESTIONS:\n- Noul: x'
jbad "two JEV-STATE lines" "need exactly one" $'JEV-STATE:\na\nJEV-STATE:\nb\nJEV-QUESTIONS:\n- Noul: x'
jbad "JEV-QUESTIONS before JEV-STATE" "'JEV-STATE:' must come before" $'JEV-QUESTIONS:\n- Noul: x\nJEV-STATE:\ns'
jbad "empty state" "JEV-STATE is empty" $'JEV-STATE:\n\n   \nJEV-QUESTIONS:\n- Noul: x'
jbad "no questions" "JEV-QUESTIONS has no questions" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n\n'
jbad "free text after JEV-QUESTIONS" "is not a '- Kind: ...' question" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Noul: x\nplease answer carefully'
jbad "unknown kind" "unknown question kind" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Maybe: x'
jbad "kind without colon" "unknown question kind" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Noul x'
jbad "Choice with 1 option" "a Choice needs 2..255 options" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Choice: which? | only'
jbad "Choice with 256 options" "a Choice needs 2..255 options" "$(printf 'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Choice: which?'; for i in $(seq 256); do printf ' | o%d' "$i"; done)"
jbad "Score without levels" "a Score needs 2..10 levels" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Score: severity'
jbad "Score with 11 levels" "a Score needs 2..10 levels" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Score: s | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11'
jbad "Noul with '|'" "a Noul is one claim with no '|'" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Noul: a | b'
jbad "empty field" "empty field" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Choice: q | a |  | b'
jbad "duplicate option" "duplicate option" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Choice: q | a | a'
jbad "duplicate level" "duplicate level" $'JEV-STATE:\ns\nJEV-QUESTIONS:\n- Score: q | low | low'
pm "$P3"; mode probe3; seat
[ "$rc" -eq 0 ] && [ "$(mj 'm["jev"]["questions"],m["jev"]["kinds"]')" = "(1, ['noul'])" ] && ok "valid one-Noul block (the probe-3 shape) -> exit 0" || bad "valid P3 (rc $rc)"
printf '# A task\n\nSEAT: jev\nSCOPE: build\n\nPreamble prose before the block is not sent.\n\n%s\n\n' "$MIX" > "$SB/p.md"; mode auto; seat
[ "$rc" -eq 0 ] && [ "$(mj 'm["jev"]["kinds"]')" = "['noul', 'choice', 'score']" ] && [ "$(hj 'j["state"]')" = "$(printf '%s' "$MIX" | sed -n 2p)" ] \
  && ok "full queue task (title, SEAT, prose, block last, trailing blank lines): only the state text is sent" || bad "task-wrapped (rc $rc)"

echo "== R: request construction =="
pm "$MIX"; mode auto; seat
[ "$(hj 'j["keys"]')" = "['model', 'questions', 'state']" ] && ok "body has exactly model, state, questions" || bad "keys $(hj 'j["keys"]')"
[ "$(hj 'j["model"],j["method"],j["content_type"],j["auth_match"]')" = "('jev-latest', 'POST', 'application/json', True)" ] && ok "POST application/json, model jev-latest, Bearer = sha256 match of the key file" || bad "hdr $(hj 'j["model"],j["content_type"],j["auth_match"]')"
python3 -I - "$SB/hits" <<'PY' && ok "questions is an id->object map: q1 noul {type,instructions}; q2 choice criteria {opt: opt}; q3 score criteria [lowest..highest]" || bad "questions shape"
import json,sys; q=json.loads(open(sys.argv[1]).read().splitlines()[-1])["questions"]
assert q=={"q1":{"type":"noul","instructions":"The failures are confined to parser.py."},
 "q2":{"type":"choice","instructions":"Which component most likely broke?","criteria":{"parser":"parser","lexer":"lexer","runner":"runner"}},
 "q3":{"type":"score","instructions":"Severity of the regression","criteria":["none","minor","moderate","major","critical"]}}, q
PY
[ "$(hj 'j["state"]')" = "$(printf '%s' "$MIX" | sed -n 2p)" ] && ok "state is the JEV-STATE text, verbatim (UTF-8 and quotes intact)" || bad "state $(hj 'j["state"]')"
mode redirect; : > "$SB/hits"; seat
[ "$rc" -eq 3 ] && grep -q "redirect refused" "$SB/m.json" && [ "$(hits)" -eq 1 ] && ok "307 redirect refused: one hit only, key never re-sent" || bad "redirect (rc $rc, hits $(hits))"

echo "== D: typed decisions =="
fresh; pm "$P3"; mode probe3; seat
grep -q "^Q1 (Noul): On a clear day the sky appears blue.$" "$SB/o.md" && grep -q "^  Decision: the claim holds.$" "$SB/o.md" && grep -q "^  Probability the claim holds: 0.92$" "$SB/o.md" \
  && ok "REAL probe-3 reply: question echoed, 'the claim holds', probability 0.92" || bad "p3 render: $(cat "$SB/o.md")"
[ "$(mj 'm["model"],m["model_requested"],m["model_source"]')" = "('jev-1.14.0', 'jev-latest', 'response')" ] && ok "jev-latest resolved to jev-1.14.0 (recorded from the reply)" || bad "model $(mj 'm["model"]')"
grep -q "never grants the verified stamp" "$SB/o.md" && ok "out header: Jev never grants the verified stamp" || bad "header"
pm "$MIX"; mode auto; seat
[ "$(mj '[(d["id"],d["type"],d["decision"]) for d in m["decisions"]]')" = "[('q1', 'noul', 'holds'), ('q2', 'choice', 'parser'), ('q3', 'score', 'critical')]" ] && ok "documented-synthetic: decisions noul holds / choice parser / score critical" || bad "decs $(mj 'm["decisions"]')"
grep -q "^  Probability of that option: 0.70$" "$SB/o.md" && grep -q "^  Nearest level: critical (level 5 of 5, lowest = 1)$" "$SB/o.md" && grep -q "^  Score: 4 of 4 — exactly at critical$" "$SB/o.md" && ok "choice probability 0.70; integer score 4 -> '4 of 4 — exactly at critical', level 5 of 5" || bad "render mix"
[ "$(mj 'm["decisions"][2]["position"],m["decisions"][2]["probability_weighted_position"],m["decisions"][2]["probabilities"]')" = "(1.0, 0.9, [0.0, 0.0, 0.0, 0.4, 0.6])" ] && grep -q "^  Normalized position (score / 4), 0 = lowest .. 1 = highest: 1.00$" "$SB/o.md" && grep -q "Probability-weighted position, 0 = lowest .. 1 = highest: 0.90" "$SB/o.md" \
  && ok "position = score/(n-1) = 1.00; probability-weighted sum p_i*i/(n-1) = (0.4*3+0.6*4)/4 = 0.90 kept separately" || bad "position $(mj 'm["decisions"][2]')"

grep -q "Jev's confidence: 0.80" "$SB/o.md" && ok "confidence reported" || bad "confidence"
echo "== FS: fractional scores (the semantics 019 proved live: 3.95 on a 5-level Score) =="
fresh; pm "$MIX"
rawn() { ls "$FB/work/jev-raw" 2>/dev/null | wc -l; }
mode score019; seat
[ "$rc" -eq 0 ] && [ "$(mj '(lambda d: (d["score"],d["levels"],d["level"],d["decision"],d["position"],"probability" in d))(m["decisions"][2])')" = "(3.95, 5, 4, 'critical', 0.9875, False)" ] \
  && ok "score 3.95 (bare, no legend/probabilities) accepted: nearest level critical, position 3.95/4 = 0.9875" || bad "score019 (rc $rc): $(mj 'm.get("error") or m["decisions"][2]')"
grep -q "^  Score: 3.95 of 4 — between major and critical, near critical$" "$SB/o.md" && grep -q "^  Scale: 0 = none .. 4 = critical (none | minor | moderate | major | critical)$" "$SB/o.md" \
  && grep -q "^  Normalized position (score / 4), 0 = lowest .. 1 = highest: 0.99$" "$SB/o.md" && ! grep -q "Probability of the nearest" "$SB/o.md" \
  && ok "rendered: '3.95 of 4 — between major and critical, near critical', the scale, normalized 0.99" || bad "score019 render: $(cat "$SB/o.md")"
pm "JEV-STATE:
s

JEV-QUESTIONS:
- Noul: c
- Score: completeness | None | Low | Medium | High | Complete"; seat
grep -q "^  Score: 3.95 of 4 — between High and Complete, near Complete$" "$SB/o.md" && ok "the task's own example: '3.95 of 4 — between High and Complete, near Complete'" || bad "example: $(cat "$SB/o.md")"
pm "$MIX"; mode score_zero; seat
[ "$rc" -eq 0 ] && [ "$(mj '(lambda d: (d["score"],d["level"],d["decision"],d["position"]))(m["decisions"][2])')" = "(0.0, 0, 'none', 0.0)" ] && grep -q "^  Score: 0 of 4 — exactly at none$" "$SB/o.md" \
  && ok "exact 0.0 accepted: 'exactly at none', position 0.00" || bad "score_zero (rc $rc): $(mj 'm.get("error")')"
mode score_top; seat
[ "$rc" -eq 0 ] && [ "$(mj '(lambda d: (d["score"],d["level"],d["decision"],d["position"]))(m["decisions"][2])')" = "(4.0, 4, 'critical', 1.0)" ] && grep -q "^  Score: 4 of 4 — exactly at critical$" "$SB/o.md" \
  && ok "exact n-1 (4.0) accepted: 'exactly at critical', position 1.00" || bad "score_top (rc $rc): $(mj 'm.get("error")')"
[ "$(rawn)" -eq 0 ] && ok "no raw reply file on parsed exits" || bad "raw file on ok exit"
for v in score_over score_neg score_str score_missing; do
  mode $v; seat
  [ "$rc" -eq 4 ] && [ "$(mj 'm["exit"],m["cost_usd"]')" = "('unparsed', 1.193e-05)" ] && grep -q "not a number on the 0..4 scale of the 5 levels sent" "$SB/m.json" && [ ! -s "$SB/o.md" ] && [ -f "$(mj 'm["raw_reply"]')" ] \
    && ok "$v -> exit 4 unparsed (out of range / non-numeric / missing refused), raw reply kept" || bad "$v (rc $rc): $(mj 'm.get("error")')"
done

echo "== RR: raw reply preserved on every unparsed exit =="
fresh; pm "$MIX"; mode score_over; seat
rp=$(mj 'm["raw_reply"]')
[ "$rc" -eq 4 ] && [ "$(dirname "$rp")" = "$FB/work/jev-raw" ] && [ "$(stat -c %a "$rp")" = 600 ] && [ "$(stat -c %a "$FB/work/jev-raw")" = 700 ] && ok "raw reply at work/jev-raw/ (dir 700, file 600), path in meta raw_reply" || bad "raw path $rp"
python3 -I - "$rp" "$SB/hits" <<'PY' && ok "raw file is the fake's exact reply (score 4.01 for q3), byte count in meta" || bad "raw content"
import json,sys; r=json.load(open(sys.argv[1])); assert r["answers"]["q3"]=={"type":"score","score":4.01}, r; assert r["usage"]=={"input_tokens":284,"output_tokens":21}
PY
[ "$(mj 'm["raw_reply_bytes"]')" = "$(stat -c %s "$rp")" ] && [ "$(mj '"raw_reply_key_scrubbed" in m')" = False ] || bad "raw bytes / scrub flag"
mode garbage; seat
[ "$rc" -eq 4 ] && [ "$(cat "$(mj 'm["raw_reply"]')")" = "not json" ] && [ "$(mj 'm["raw_reply"]')" != "$rp" ] && ok "non-JSON reply preserved verbatim under a new name (never overwrites)" || bad "garbage raw"
mode keyecho; seat
kp=$(mj 'm["raw_reply"]')
[ "$rc" -eq 4 ] && ! grep -qF -- "$FAKEKEY" "$kp" && grep -q "echo \[key\] end" "$kp" && [ "$(mj 'm["raw_reply_key_scrubbed"]')" = True ] && ok "a reply that echoes the bearer: key replaced by [key] in the raw file, flagged in meta" || bad "keyecho raw: $(cat "$kp")"
mode vendorerr; seat
[ "$rc" -eq 3 ] && [ "$(mj '"raw_reply" in m')" = False ] && ok "non-unparsed exits (vendor error) keep no raw file" || bad "vendorerr raw"
if grep -rqF -- "$FAKEKEY" "$FB/work" "$SB/m.json"; then bad "fake key in work/"; else ok "fake key in no raw reply file"; fi

echo "== B: billing, both paths =="
fresh; pm "$P3"; mode probe3; seat
[ "$(mj 'm["in_tokens"],m["out_tokens"],m["cost_usd"],m["usage_reported"]')" = "(284, 21, 1.193e-05, True)" ] && ok "REAL usage 284/21 -> \$0.00001193 (284 x \$0.042/M + 21 x \$0.0/M, registry CANDIDATE prices)" || bad "usage $(mj 'm["in_tokens"],m["out_tokens"],m["cost_usd"]')"
[ "$(mj 'm["price_in_per_mtok_usd"],m["price_out_per_mtok_usd"],m.get("cost_source")')" != "" ] && [ "$(mj 'm.get("cost_source")')" != "$UNREP" ] && ok "reported path: cost_source is not the unreported rule" || bad "cost_source"
pm "$MIX"; mode nousage; seat
[ "$rc" -eq 0 ] && [ "$(mj 'm["in_tokens"],m["out_tokens"],m["cost_usd"],m["cost_source"],m["usage_reported"]')" = "(None, None, 0.01, '$UNREP', False)" ] \
  && ok "MODERATOR'S RULE: no usage -> null tokens (never guessed), cost \$0.01 = planned worst case, answers still delivered" || bad "nousage (rc $rc) $(mj 'm["in_tokens"],m["cost_usd"]')"
mode badusage; seat
[ "$rc" -eq 0 ] && [ "$(mj 'm["in_tokens"],m["cost_usd"],m["cost_source"]')" = "(None, 0.01, '$UNREP')" ] && ok "non-integer usage -> same rule (null tokens, \$0.01)" || bad "badusage (rc $rc)"
mode nousage_bad; seat
[ "$rc" -eq 4 ] && [ "$(mj 'm["exit"],m["cost_usd"],m["cost_source"]')" = "('unparsed', 0.01, '$UNREP')" ] && ok "no usage AND unparseable answers -> exit 4, still billed \$0.01 (a reply that came back was paid for)" || bad "nousage_bad (rc $rc)"

echo "== F: replies that do not fit, and transport failures =="
fresh; pm "$MIX"
for v in wrongtype notoffered scorerange legendbad badprobkey missing extra; do
  mode $v; seat
  [ "$rc" -eq 4 ] && [ "$(mj 'm["exit"],m["cost_usd"]')" = "('unparsed', 1.193e-05)" ] && grep -q "did not fit the questions sent" "$SB/m.json" && [ ! -s "$SB/o.md" ] \
    && ok "$v -> exit 4 unparsed, reported usage still costed, no decisions written" || bad "$v (rc $rc): $(mj 'm.get("error")')"
done
mode garbage; seat
[ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = unparsed ] && [ -f "$SB/o.md" ] && ok "non-JSON reply -> exit 4 unparsed, out exists" || bad "garbage (rc $rc)"
mode vendorerr; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = seat-error ] && grep -q "synthetic vendor error" "$SB/m.json" && ok "error object -> exit 3 seat-error" || bad "vendorerr (rc $rc)"
mode probe1; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = http-error ] && ok "REAL probe-1 reply (HTTP 422 questions not a dict) -> exit 3 http-error" || bad "probe1 (rc $rc)"
mode probe2; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = http-error ] && ok "REAL probe-2 reply (HTTP 400 api_usage_error) -> exit 3 http-error" || bad "probe2 (rc $rc)"
mode error500; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = http-error ] && ok "HTTP 500 -> exit 3 http-error" || bad "500 (rc $rc)"
mode hang; t=$(date +%s); seat --timeout 2; d=$(( $(date +%s) - t ))
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = timeout ] && [ "$d" -le 6 ] && ok "hung endpoint -> exit 3 timeout in ${d}s" || bad "hang (rc $rc, ${d}s)"

echo "== S: size guard (state + questions > ~30,000 tokens refused before any call) =="
fresh; mode auto
{ echo "JEV-STATE:"; head -c 95000 /dev/zero | tr '\0' a; printf '\nJEV-QUESTIONS:\n- Noul: x\n'; } > "$SB/p.md"; seat
[ "$rc" -eq 3 ] && [ "$(mj 'm["exit"]')" = size-guard ] && grep -q "64K vs ~32K" "$SB/m.json" && [ "$(hits)" -eq 0 ] && ok "~31,700-token state -> exit 3 size-guard, no call" || bad "guard (rc $rc)"
rm "$FB/secrets/$S.key"; seat
[ "$rc" -eq 3 ] && [ "$(hits)" -eq 0 ] && ok "a size-guard or malformed block is refused before the key is even needed" || bad "guard order (rc $rc)"
(umask 177; printf '%s\n' "$FAKEKEY" > "$FB/secrets/$S.key")
{ echo "JEV-STATE:"; head -c 85000 /dev/zero | tr '\0' a; printf '\nJEV-QUESTIONS:\n- Noul: x\n'; } > "$SB/p.md"; seat
[ "$rc" -eq 0 ] && [ "$(hits)" -eq 1 ] && [ "$(mj 'm["jev"]["combined_tokens_est"] <= 30000')" = True ] && ok "~28,350-token state -> sent" || bad "under guard (rc $rc)"

echo "== T: templates + bin/jev_ask.py =="
fresh; mode auto
ASK() { python3 -I "$SRC/bin/jev_ask.py" "$@" > "$SB/ask.out" 2>&1; arc=$?; }
tseat() { cp "$1" "$SB/p.md"; seat; }
ASK --template claim-support --slot question="Is the parser at fault?" --slot answer="Yes, parser.py alone" --slot evidence="All failing tests import parser.py." --out "$SB/t1.md"
[ "$arc" -eq 0 ] && grep -qx "SEAT: jev" "$SB/t1.md" && tseat "$SB/t1.md" && [ "$rc" -eq 0 ] && [ "$(mj 'm["jev"]["kinds"]')" = "['noul', 'score']" ] && ok "claim-support renders; adapter accepts it (Noul + Score)" || bad "claim-support ($arc/$rc) $(cat "$SB/ask.out")"
ASK --template critique-point --slot artifact=$'def f(xs):\n    for i in range(len(xs)-1): yield xs[i]' --slot point="The loop skips the last item" --out "$SB/t2.md"
[ "$arc" -eq 0 ] && tseat "$SB/t2.md" && [ "$rc" -eq 0 ] && [ "$(mj 'm["jev"]["kinds"]')" = "['score']" ] && grep -q "Normalized position (score / 4)" "$SB/o.md" && ok "critique-point renders; adapter accepts it (Score, normalized position score/(n-1))" || bad "critique-point ($arc/$rc) $(cat "$SB/ask.out")"
ASK --template position-support --slot position="Ship on Friday" --slot evidence="All gates green." --out "$SB/t3.md"
[ "$arc" -eq 0 ] && tseat "$SB/t3.md" && [ "$rc" -eq 0 ] && [ "$(mj 'm["jev"]["kinds"]')" = "['score']" ] && ok "position-support without record: Score only (no contradiction Noul)" || bad "position-support ($arc/$rc) $(cat "$SB/ask.out")"
ASK --template position-support --slot position="Ship on Friday" --slot evidence="All gates green." --slot record="Agreed: ship after the audit." --out "$SB/t3b.md"
[ "$arc" -eq 0 ] && tseat "$SB/t3b.md" && [ "$rc" -eq 0 ] && [ "$(mj 'm["jev"]["kinds"]')" = "['score', 'noul']" ] && ok "position-support with record: adds the contradiction Noul" || bad "position-support+record ($arc/$rc) $(mj 'm["jev"]["kinds"]')"
ASK --template draft-agreement --slot claim="X causes Y" --slot draft1="X causes Y." --slot draft2="Y follows X." --slot draft3="X is unrelated to Y." --out "$SB/t4.md"
[ "$arc" -eq 0 ] && tseat "$SB/t4.md" && [ "$rc" -eq 0 ] && [ "$(mj 'm["jev"]["kinds"]')" = "['noul', 'score']" ] && grep -q "Draft 3" "$SB/t4.md" && ! grep -q "Draft 4" "$SB/t4.md" && ok "draft-agreement with 3 drafts renders; optional drafts 4-5 omitted" || bad "draft-agreement ($arc/$rc)"
for t in claim-support critique-point position-support draft-agreement; do
  for r in "(single|one) (central )?(claim|point)" "trimmed" "counting" "date arithmetic" "indirect"; do grep -qiE "$r" "$SRC/templates/jev/$t.md" || bad "$t lacks rule '$r'"; done
done; ok "every template states the five rules (single claim, trimmed evidence, no counting, no date arithmetic, no indirect phrasing)"
ASK --template no-such --slot a=b --out "$SB/r1.md"
[ "$arc" -eq 2 ] && grep -q "unknown template" "$SB/ask.out" && [ ! -e "$SB/r1.md" ] && ok "unknown template refused, nothing written" || bad "unknown template ($arc)"
ASK --template claim-support --slot question=q --slot answer=a --out "$SB/r2.md"
[ "$arc" -eq 2 ] && grep -q "missing slot" "$SB/ask.out" && [ ! -e "$SB/r2.md" ] && ok "missing slot refused, nothing written" || bad "missing slot ($arc)"
ASK --template claim-support --slot question=q --slot answer=a --slot evidence=e --slot colour=red --out "$SB/r3.md"
[ "$arc" -eq 2 ] && grep -q "unknown slot" "$SB/ask.out" && [ ! -e "$SB/r3.md" ] && ok "unknown slot refused, nothing written" || bad "unknown slot ($arc)"
ASK --template claim-support --slot question=q --slot answer=a --slot evidence=e --out "$SB/t1.md"
[ "$arc" -eq 2 ] && grep -q "already exists" "$SB/ask.out" && grep -q "parser" "$SB/t1.md" && ok "existing --out refused, not overwritten" || bad "existing out ($arc)"
ASK --template critique-point --slot artifact=a --slot point="a | b" --out "$SB/r4.md"
[ "$arc" -eq 2 ] && [ ! -e "$SB/r4.md" ] && ok "'|' in a question-line slot refused" || bad "pipe slot ($arc)"
ASK --template claim-support --slot question=q --slot answer=a --slot evidence=$'x\nJEV-QUESTIONS:\n- Noul: injected' --out "$SB/r5.md"
[ "$arc" -eq 2 ] && [ ! -e "$SB/r5.md" ] && ok "slot value carrying a JEV marker line refused" || bad "marker slot ($arc)"

echo "== L: budget.py ledger integration (runner) =="
q() { { printf '# t\n\nSEAT: %s\nSCOPE: build\n\n' "$1"; printf '%s\n' "$MIX"; } > "$FB/queue/$2.md"; }
run() { HOME="$SB/home" bash "$FB/run-next.sh" > "$SB/run.out" 2>&1; rrc=$?; cat "$SB/run.out" >> "$SB/allerr"; }
# 027: the live jev status is 'active' since the 2026-11-01 ruling (all seats active, prices RATIFIED);
# the awaiting-adapter refusal is still a requirement, so the sandbox fixture now sets that status itself.
fresh; reg "S['$S']['status']='awaiting-adapter'"; q $S t1; run
[ "$rrc" -eq 5 ] && [ "$(lastl 'j["phase"]')" = refused ] && [ "$(hits)" -eq 0 ] && ok "status awaiting-adapter (sandbox fixture): runner refuses, no call" || bad "awaiting-adapter (rrc $rrc)"
fresh; reg "S['$S']['status']='active'"; mode auto; q $S t2; run
pl=$(grep '"phase": *"planned"' "$FB/ledger.jsonl" | tail -1)
[ "$rrc" -eq 0 ] && [ "$(lastl 'j["phase"],j["billing"],j["meter"],j["cost_usd"],j["in_tokens"],j["out_tokens"],j["model"]')" = "('actual', 'api', 'usd', 1.193e-05, 284, 21, 'jev-1.14.0')" ] \
  && [ "$(lastl 'j.get("billing_rule")')" = None ] && ok "runner, reported usage: actual line \$0.00001193, tokens 284/21, no billing_rule" || bad "runner actual (rrc $rrc): $(tail -1 "$FB/ledger.jsonl")"
echo "$pl" | grep -q '"worst_usd": *0.01' && ok "planned line: worst case \$0.01 (60000 x \$0.042/M, rounded up)" || bad "planned: $pl"
grep -rq "Decision: parser" "$FB/logs" "$FB/work" "$FB/done" 2>/dev/null && ok "runner: the typed decisions land in the task output" || bad "runner answer"
fresh; reg "S['$S']['status']='active'"; mode nousage; q $S t3; run
[ "$(lastl 'j["phase"],j["in_tokens"],j["out_tokens"],j["cost_usd"],j["worst_usd"],j["cost_source"],j["billing_rule"]')" = "('actual', None, None, 0.01, 0.01, '$UNREP', 'moderator-unreported-worst-case')" ] \
  && ok "runner, MODERATOR'S RULE: actual line with null tokens, \$0.01 = worst, billing_rule recorded" || bad "runner unreported (rrc $rrc): $(tail -1 "$FB/ledger.jsonl")"
fresh; reg "S['$S']['status']='active'"; rm "$FB/secrets/$S.key"; q $S t4; run
[ "$rrc" -eq 5 ] && [ "$(hits)" -eq 0 ] && ok "runner pre-flight: no key file -> refused, no call" || bad "pf key (rrc $rrc)"
fresh; reg "S['$S']['status']='active'"; q $S t5
pf=$(python3 -I "$FB/bin/budget.py" preflight "$FB" "$FB/queue/t5.md" t5 "$(date -Is)"); read -r _ cid _ worst _ <<< "$pf"
src=$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["seats"]["jev"]["api"]["price_source"])' "$FB/seats/registry.json")
mkm() {  # mkm <file> <seat> <in|null> <out|null> <cost> <cost_source> <price_source>
  python3 -I -c 'import json,sys
f,s,i,o,c,cs,ps=sys.argv[1:]; n=lambda x: None if x=="null" else int(x)
json.dump({"seat":s,"model":"jev-1.14.0","started":"s","finished":"f","in_tokens":n(i),"out_tokens":n(o),"cost_usd":float(c),
 "cost_source":cs,"price_source":ps,"billing":"api","meter":"usd","exit":"ok"},open(f,"x"))' "$@"; }
act() { python3 -I "$FB/bin/budget.py" actual "$FB" t5 "$1" "$cid" "$worst" > "$SB/act.out"; arc=$?; }
n0=$(wc -l < "$FB/ledger.jsonl")
mkm "$FB/logs/x1.json" jev 284 null 0.01 "$UNREP" "$src"; act logs/x1.json
[ "$arc" -eq 4 ] && grep -q "must carry null tokens" "$SB/act.out" && ok "budget.actual: jev rule with a token count present -> exit 4" || bad "x1 ($arc)"
mkm "$FB/logs/x2.json" jev null null 0.005 "$UNREP" "$src"; act logs/x2.json
[ "$arc" -eq 4 ] && ok "budget.actual: jev rule with cost != planned worst -> exit 4" || bad "x2 ($arc)"
mkm "$FB/logs/x3.json" jev null null "$worst" "$UNREP" "someone else's prices"; act logs/x3.json
[ "$arc" -eq 4 ] && ok "budget.actual: jev rule with a foreign price_source -> exit 4" || bad "x3 ($arc)"
mkm "$FB/logs/x4.json" jev null null "$worst" "estimated" "$src"; act logs/x4.json
[ "$arc" -eq 4 ] && ok "budget.actual: jev null tokens under any other cost_source -> exit 4" || bad "x4 ($arc)"
[ "$(wc -l < "$FB/ledger.jsonl")" -eq "$n0" ] && ok "no ledger line from any refused meta" || bad "refused meta wrote a line"
dsrc=$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["seats"]["deepseek"]["api"]["price_source"])' "$FB/seats/registry.json")
python3 -I -c 'import json,sys; json.dump({"seat":"deepseek","model":"m","started":"s","finished":"f","in_tokens":None,"out_tokens":None,"cost_usd":float(sys.argv[2]),"cost_source":"unreported-billed-at-worst-case","price_source":sys.argv[3],"billing":"api","meter":"usd","exit":"ok"},open(sys.argv[1],"x"))' "$FB/logs/x5.json" "$worst" "$dsrc"
act logs/x5.json
[ "$arc" -eq 4 ] && grep -q "missing integer tokens" "$SB/act.out" && ok "budget.actual: the rule is jev-only (deepseek with the same cost_source -> exit 4)" || bad "x5 ($arc) $(cat "$SB/act.out")"
mkm "$FB/logs/x6.json" jev null null "$worst" "$UNREP" "$src"; act logs/x6.json
[ "$arc" -eq 0 ] && [ "$(lastl 'j["in_tokens"],j["cost_usd"],j["billing_rule"]')" = "(None, $worst, 'moderator-unreported-worst-case')" ] && ok "budget.actual: well-formed jev rule meta accepted (null tokens, \$$worst)" || bad "x6 ($arc) $(cat "$SB/act.out")"
mkm "$FB/logs/x7.json" jev 284 21 0.00001193 api "$src"; act logs/x7.json
[ "$arc" -eq 0 ] && ok "budget.actual: normal jev meta (284/21 x registry prices) accepted" || bad "x7 ($arc) $(cat "$SB/act.out")"

echo "== LG: legend shapes (016d; the REAL 019b reply, legend sent as an OBJECT keyed \"0\"..\"n-1\") =="
fresh; pm "$(cat "$HERE/fixtures/live019b_prompt.md")"; mode live019b; seat
[ "$rc" -eq 0 ] && [ "$(mj '[(d["id"],d["type"],d["decision"]) for d in m["decisions"]]')" = "[('q1', 'noul', 'holds'), ('q2', 'score', 'Complete'), ('q3', 'choice', 'The 2026 snapshot')]" ] \
  && ok "REAL 019b reply parses in full: noul holds / score Complete / choice 'The 2026 snapshot'" || bad "live019b (rc $rc): $(mj 'm.get("error") or m.get("decisions")')"
[ "$(mj '(lambda d: (d["score"],d["levels"],d["level"],d["position"],d["probabilities"],d["probability_weighted_position"]))(m["decisions"][1])')" = "(3.94, 5, 4, 0.985, [0.0, 0.0, 0.0, 0.05, 0.95], 0.9875)" ] \
  && ok "019b score: 3.94 -> nearest level 4 (Complete), position 0.985, index-keyed probabilities in level order, weighted 0.9875" || bad "019b score $(mj 'm["decisions"][1]')"
grep -q "^  Probability the claim holds: 0.98$" "$SB/o.md" && grep -q "^  Score: 3.94 of 4 — between High and Complete, near Complete$" "$SB/o.md" \
  && grep -q "^  Probability of that option: 1.00$" "$SB/o.md" && grep -q "^  Jev's confidence: 0.96$" "$SB/o.md" \
  && ok "019b rendered: noul 0.98, '3.94 of 4 — between High and Complete, near Complete', choice probability 1.00, confidence 0.96" || bad "019b render: $(cat "$SB/o.md")"
[ "$(mj 'm["in_tokens"],m["out_tokens"],m["model"]')" = "(550, 90, 'jev-1.14.0')" ] && [ "$(rawn)" -eq 0 ] && ok "019b usage 550/90 recorded; no raw file on the parsed exit" || bad "019b usage/raw"
mode lg_array; seat
[ "$rc" -eq 0 ] && [ "$(mj 'm["decisions"][1]["decision"]')" = Complete ] && ok "lg_array: the documented array legend of the same labels still accepted" || bad "lg_array (rc $rc): $(mj 'm.get("error")')"
for v in lg_missing lg_extra lg_gap lg_padded lg_wronglabel lg_nonstring lg_array_wronglabel lg_array_short; do
  mode $v; seat
  [ "$rc" -eq 4 ] && [ "$(mj 'm["exit"]')" = unparsed ] && grep -q "q2: legend does not match the 5 levels sent" "$SB/m.json" && [ ! -s "$SB/o.md" ] && [ -f "$(mj 'm["raw_reply"]')" ] \
    && ok "$v -> exit 4 unparsed (legend refused), raw reply kept" || bad "$v (rc $rc): $(mj 'm.get("error")')"
done

echo "== X: no key material anywhere; loopback only =="
cat "$SB/hits" >> "$SB/allhits"
if grep -rqF -- "$FAKEKEY" "$SB/allmeta" "$SB/allerr" "$FB/ledger.jsonl" "$FB/logs" "$FB/done" "$FB/work" "$SB/allhits" "$SB"/t*.md 2>/dev/null; then bad "fake key found in output"; else ok "fake key appears in no meta, out, stderr, log, ledger, rendered task or fake-server record"; fi
grep -q '"auth_match": true' "$SB/allhits" && ! grep -q "ts-FAKE" "$SB/allhits" && ok "fake server records only a sha256 match flag" || bad "hits file"

echo "== P: the live tree =="
python3 -I - "$SRC/seats/registry.json" "$SRC/seats/registry.json.bak-pre-016c-20261101" <<'PY' && ok "live registry jev entry vs pre-016c: only an appended facts_status and status awaiting-adapter -> active (2026-11-01 ruling); prices 0.042/0.0, price_status as before" || bad "live registry diff"
import json,sys
new,old=(json.load(open(p)) for p in sys.argv[1:3])
a,b=new["seats"]["jev"],old["seats"]["jev"]
assert a["api"]["facts_status"].startswith(b["api"]["facts_status"]) and len(a["api"]["facts_status"])>len(b["api"]["facts_status"])
assert "3.95" in a["api"]["facts_status"][len(b["api"]["facts_status"]):]
a["api"].pop("facts_status"); b["api"].pop("facts_status")
# 027: status flipped by the 2026-11-01 ruling (all seats active); nothing else in the entry may move
assert (b.pop("status"),a.pop("status"))==("awaiting-adapter","active")
assert a==b
assert (a["api"]["price_in_per_mtok_usd"],a["api"]["price_out_per_mtok_usd"])==(0.042,0.0)
for k in new["seats"]:
    if k!="jev": assert new["seats"][k]==old["seats"][k], k
assert {k:v for k,v in new.items() if k!="seats"}=={k:v for k,v in old.items() if k!="seats"}
PY
python3 -I - "$SRC/seats/registry.json" "$SRC/seats/registry.json.bak-pre-016d-20261101" <<'PY' && ok "live registry vs pre-016d: only jev facts_status appended (LEGEND SHAPE) and status awaiting-adapter -> active (2026-11-01 ruling); prices unchanged" || bad "live registry diff (016d)"
import json,sys
new,old=(json.load(open(p)) for p in sys.argv[1:3])
a,b=new["seats"]["jev"],old["seats"]["jev"]
fa,fb=a["api"].pop("facts_status"),b["api"].pop("facts_status")
assert fa.startswith(fb) and "LEGEND SHAPE" in fa[len(fb):]
assert (b.pop("status"),a.pop("status"))==("awaiting-adapter","active")  # 027: 2026-11-01 ruling
assert a==b
for k in new["seats"]:
    if k!="jev": assert new["seats"][k]==old["seats"][k], k
assert {k:v for k,v in new.items() if k!="seats"}=={k:v for k,v in old.items() if k!="seats"}
PY
grep -q 'jev_systemone.py" jev' "$SRC/seats/jev.sh" && ! grep -q 'api_seat.py' "$SRC/seats/jev.sh" && ok "jev.sh execs jev_systemone.py" || bad "wrapper"
grep -q 'api_seat.py" deepseek' "$SRC/seats/deepseek.sh" && ! grep -l jev_systemone "$SRC"/seats/{deepseek,gemini_api,grok,perplexity}.sh >/dev/null 2>&1 && ok "other api wrappers untouched by the rewire" || bad "other wrappers"
[ "$(stat -c %a "$SRC/secrets" 2>/dev/null)" != "" ] && [ ! -e "$SRC/secrets/jev.key" ] && echo "  (live secrets/jev.key absent: Jev cannot be called from the live tree until Dan installs it)" || true

echo
echo "phase8: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
