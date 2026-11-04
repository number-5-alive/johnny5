# Role card: codex (v1, task 012, 2026-11-01)

Seat id `codex`, ledger seat `codex`, adapter `seats/codex.sh` (OpenAI Codex CLI 0.166.0, `codex exec`).
Billing class: **subscription** (ChatGPT sign-in), metered in **tokens**. The CLI reports no dollar figure, so none is recorded. Status: **active** — logged in on the commissioner's ChatGPT subscription; default model `gpt-6-luna`; smoke passed 2026-11-01. (Status refreshed 2026-11-03 from the ratified registry.)

## Declared strengths (vendor and general claims, not yet tested here)
- Code reading, code review, and second opinions on code.
- An independent critic from a different model family than Claude or qwen.

## Proven strengths
- Login and smoke call proven live 2026-11-01 in the full-roster smoke. Session-work strengths remain to be proven.

## Turn profile
- Word-only: read-only sandbox, ephemeral, user config and rules ignored, shell, exec, browser, apps, plugins and similar features disabled, empty scratch directory.
- Tokens come from `turn.completed.usage` (input, cached input, output, reasoning output).
- Caps: budget.yaml codex.* (pacing). The CLI exposes no per-call output cap flag, so overages are recorded after the call (cap_exceeded), not prevented. The timeout is the hard stop.
