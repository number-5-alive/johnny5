#!/usr/bin/env bash
# Robot Factory seat adapter: Google Gemini CLI (Login with Google). Phase 5, task 012, 2026-11-01.
# Word-only, token-metered subscription seat. Same contract as claude_code.sh:
#
#   gemini_cli.sh --prompt <file.md> --out <reply.md> --meta <meta.json>
#            [--seat <id>] [--max-out-tokens <n>] [--budget <budget.yaml>] [--timeout <s>]
#
# Exit: 0 ok | 2 capped (unused: the CLI has no output-cap flag) | 3 seat error,
# no auth, API key set, or timeout | 4 unparsed or tokens/model missing.
# meta.json is written in every case (exclusive create); an existing --meta is
# refused before any call. Tokens only from what the CLI reports; no dollar
# figure exists, so cost_usd is null, cost_source "not-reported-tokens-only".
# No auth: refused in the pre-check, before any model call. GEMINI_BIN: test hook only.
# The work is done by seats/token_seat.py (shared with the other token seat).
set -u
export PATH="$HOME/.local/bin:$PATH"
HERE=$(cd "$(dirname "$0")" && pwd)
SEAT=gemini-cli PROMPT= OUT= META= MAXOUT= BUDGET="$HERE/../budget.yaml" TIMEOUT_S=${TIMEOUT_S:-900}
while [ $# -gt 0 ]; do
  case "$1" in
    --seat) SEAT=$2; shift 2;;   --prompt) PROMPT=$2; shift 2;;
    --out) OUT=$2; shift 2;;     --meta) META=$2; shift 2;;
    --max-out-tokens) MAXOUT=$2; shift 2;;
    --budget) BUDGET=$2; shift 2;;  --timeout) TIMEOUT_S=$2; shift 2;;
    *) echo "gemini_cli.sh: unknown arg $1" >&2; exit 3;;
  esac
done
[ -n "$PROMPT" ] && [ -n "$OUT" ] && [ -n "$META" ] && [ -r "$PROMPT" ] \
  || { echo "gemini_cli.sh: need readable --prompt, plus --out and --meta" >&2; exit 3; }
[ -e "$META" ] || [ -L "$META" ] \
  && { echo "gemini_cli.sh: --meta $META already exists; meta is never overwritten" >&2; exit 3; }
exec python3 -I "$HERE/token_seat.py" gemini_cli "$HERE/../bin" "$PROMPT" "$OUT" "$META" \
  "$SEAT" "$MAXOUT" "$BUDGET" "$TIMEOUT_S" < /dev/null
