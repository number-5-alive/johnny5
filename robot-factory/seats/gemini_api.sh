#!/usr/bin/env bash
# Robot Factory seat adapter: gemini_api (api seat, real dollars). Phase 6, task 014, 2026-11-01.
# Thin wrapper over seats/api_seat.py; same contract as the other adapters:
#
#   gemini_api.sh --prompt <file.md> --out <reply.md> --meta <meta.json>
#            [--seat <id>] [--max-out-tokens <n>] [--budget <budget.yaml>] [--timeout <s>]
#
# Exit: 0 ok | 2 capped | 3 no/bad key file, unconfigured, seat error or timeout |
# 4 unpriced-api, unparsed or usage missing. meta.json is written in every case
# (exclusive create); an existing --meta is refused before any call.
# Key: ONLY secrets/gemini_api.key (mode 600), never an env var. See seats/cards/gemini_api.md.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
SEAT=gemini-api PROMPT= OUT= META= MAXOUT= BUDGET="$HERE/../budget.yaml" TIMEOUT_S=300
while [ $# -gt 0 ]; do
  case "$1" in
    --seat) SEAT=$2; shift 2;;   --prompt) PROMPT=$2; shift 2;;
    --out) OUT=$2; shift 2;;     --meta) META=$2; shift 2;;
    --max-out-tokens) MAXOUT=$2; shift 2;;
    --budget) BUDGET=$2; shift 2;;  --timeout) TIMEOUT_S=$2; shift 2;;
    *) echo "gemini_api.sh: unknown arg $1" >&2; exit 3;;
  esac
done
[ -n "$PROMPT" ] && [ -n "$OUT" ] && [ -n "$META" ] && [ -r "$PROMPT" ] \
  || { echo "gemini_api.sh: need readable --prompt, plus --out and --meta" >&2; exit 3; }
[ -e "$META" ] || [ -L "$META" ] \
  && { echo "gemini_api.sh: --meta $META already exists; meta is never overwritten" >&2; exit 3; }
exec env -i PATH=/usr/bin:/bin HOME="$HOME" python3 -I "$HERE/api_seat.py" gemini_api "$HERE/../bin" "$PROMPT" "$OUT" "$META" \
  "$SEAT" "$MAXOUT" "$BUDGET" "$TIMEOUT_S" < /dev/null
