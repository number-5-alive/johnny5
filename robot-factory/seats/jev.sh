#!/usr/bin/env bash
# Robot Factory seat adapter: jev (api seat, real dollars). Phase 6, task 014; rewired
# by task 016b (2026-11-01) to seats/jev_systemone.py (TypeSafe SystemOne typed
# questions; the prompt must carry one JEV-STATE / JEV-QUESTIONS block, see
# templates/jev/README.md). Same contract as the other adapters:
#
#   jev.sh --prompt <file.md> --out <reply.md> --meta <meta.json>
#            [--seat <id>] [--max-out-tokens <n>] [--budget <budget.yaml>] [--timeout <s>]
#
# Exit: 0 ok | 2 capped | 3 no/bad key file, unconfigured, malformed JEV block,
# size guard, seat error or timeout | 4 unpriced-api or unparsed. No usage in the
# reply is billed at the planned worst case (MODERATOR'S RULE, null tokens). meta.json is written in every case
# (exclusive create); an existing --meta is refused before any call.
# Key: ONLY secrets/jev.key (mode 600), never an env var. See seats/cards/jev.md.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
SEAT=jev PROMPT= OUT= META= MAXOUT= BUDGET="$HERE/../budget.yaml" TIMEOUT_S=300
while [ $# -gt 0 ]; do
  case "$1" in
    --seat) SEAT=$2; shift 2;;   --prompt) PROMPT=$2; shift 2;;
    --out) OUT=$2; shift 2;;     --meta) META=$2; shift 2;;
    --max-out-tokens) MAXOUT=$2; shift 2;;
    --budget) BUDGET=$2; shift 2;;  --timeout) TIMEOUT_S=$2; shift 2;;
    *) echo "jev.sh: unknown arg $1" >&2; exit 3;;
  esac
done
[ -n "$PROMPT" ] && [ -n "$OUT" ] && [ -n "$META" ] && [ -r "$PROMPT" ] \
  || { echo "jev.sh: need readable --prompt, plus --out and --meta" >&2; exit 3; }
[ -e "$META" ] || [ -L "$META" ] \
  && { echo "jev.sh: --meta $META already exists; meta is never overwritten" >&2; exit 3; }
exec env -i PATH=/usr/bin:/bin HOME="$HOME" python3 -I "$HERE/jev_systemone.py" jev "$HERE/../bin" "$PROMPT" "$OUT" "$META" \
  "$SEAT" "$MAXOUT" "$BUDGET" "$TIMEOUT_S" < /dev/null
