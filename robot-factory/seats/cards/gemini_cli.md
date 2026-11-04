# Role card: gemini_cli (v1, task 012, 2026-11-01)

Seat id `gemini_cli`, ledger seat `gemini-cli`, adapter `seats/gemini_cli.sh` (Google Gemini CLI 0.66.0, headless `-p`, `-o json`).
Billing class: **subscription** (Login with Google), metered in **tokens**. The CLI reports no dollar figure, so none is recorded. Status: **awaiting-login** (Dan runs `gemini` once and signs in).

## Declared strengths (vendor and general claims, not yet tested here)
- Long context, broad general knowledge.
- An independent critic from a different model family.

## Proven strengths
- None yet. Unproven: no scribe record holds a gemini call.

## Turn profile
- Word-only: `--approval-mode plan` (read-only) held by `--skip-trust`, extensions off, empty scratch directory, no API key accepted.
- Tokens come from `stats.models[<model>].tokens` (prompt, candidates, cached, thoughts). The model name is the key the CLI reports.
- Caps: budget.yaml gemini_cli.* (pacing). No per-call output cap flag, so overages are recorded after the call (cap_exceeded). The timeout is the hard stop.
