# Role card: Gemini API (AI Studio key) (`gemini_api`, api seat, task 014, 2026-11-01)

**Status: active.** Dedicated Factory key provisioned by Dan 2026-11-01 (paid Tier 1 project, billing linked); prices ratified by Dan 2026-11-01. (Status refreshed 2026-11-03 from the ratified registry.)

- Role: general word seat on the AI Studio key route. **Not** `gemini_cli` (that is the subscription OAuth seat, unchanged).
- Billing: **api** (real dollars, counted against `api_monthly_ceiling_usd`, its own tally, never added to the others).
- Meter: **tokens-priced-to-usd**: `cost_usd = in_tokens x price_in + out_tokens x price_out (+ per-call fee)`, tokens only from the vendor's reported usage; no usage = exit 4, nothing guessed.
- Key path: `~/robot-factory/secrets/gemini_api.key` (Dan creates it at his own terminal, `chmod 600`; never an env var). See `secrets/README.md`.
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/openai` (OpenAI-compatible route; confirmed 2026-11-01)
- Model: `gemini-3.8-flash`
- Prices: input $0.75, output $3.75 per Mtok. **RATIFIED** by Dan 2026-11-01 (paid branch; the free-tier branch is not used).
- Adapter: `seats/gemini_api.sh` -> `seats/api_seat.py` (word-only, no tools, SCOPE: build widens nothing).
- Note: Ledger seat id `gemini-api` (task line `SEAT: gemini_api`).

## Declared strengths (claims, not proven)
- Claim (vendor, UNVERIFIED): long context and a cheap fast tier.
- Thinking models may bill reasoning tokens outside `completion_tokens`; the core bills `total_tokens - prompt_tokens` as output when that is larger.

## Proven strengths
- Activated and smoke-tested live 2026-11-01 in the full-roster smoke. Capability claims above remain declared, not yet proven in session work.
