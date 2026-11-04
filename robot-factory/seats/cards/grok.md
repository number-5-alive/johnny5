# Role card: Grok (xAI) (`grok`, api seat, task 014, 2026-11-01)

**Status: active.** Key and $5 Prototype credits provisioned by Dan 2026-11-01; prices ratified by Dan 2026-11-01. (Status refreshed 2026-11-03 from the ratified registry.)

- Role: general word seat.
- Billing: **api** (real dollars, counted against `api_monthly_ceiling_usd`, its own tally, never added to the others).
- Meter: **tokens-priced-to-usd**: `cost_usd = in_tokens x price_in + out_tokens x price_out (+ per-call fee)`, tokens only from the vendor's reported usage; no usage = exit 4, nothing guessed.
- Key path: `~/robot-factory/secrets/grok.key` (Dan creates it at his own terminal, `chmod 600`; never an env var). See `secrets/README.md`.
- Endpoint: `https://api.x.ai/v1` (OpenAI-compatible; confirmed 2026-11-01)
- Model: `grok-4.7` (current flagship; grok-4 was retired May 2026)
- Prices: input $2.00, output $6.00 per Mtok. **RATIFIED** by Dan 2026-11-01. (Rates double at 200K+ prompts; the 60K input cap keeps calls under that line.)
- Adapter: `seats/grok.sh` -> `seats/api_seat.py` (word-only, no tools, SCOPE: build widens nothing).

## Declared strengths (claims, not proven)
- Claim (vendor, UNVERIFIED): OpenAI-compatible chat API.

## Proven strengths
- Activated and smoke-tested live 2026-11-01 in the full-roster smoke. Capability claims above remain declared, not yet proven in session work.
