# Role card: Perplexity (`perplexity`, api seat, task 014, 2026-11-01)

**Status: active** (flipped by the moderator 2026-11-01 after task 021 landed the responses shape and Dan re-ratified prices; re-smoke 022 queued).

- Role: **search specialist** (Sonar via the Agent API).
- Billing: **api** (real dollars, counted against `api_monthly_ceiling_usd`, its own tally, never added to the others).
- Meter: **tokens-priced-to-usd**: `cost_usd = in_tokens x price_in + out_tokens x price_out (+ per-call fee)`, tokens only from the vendor's reported usage; no usage = exit 4, nothing guessed. A vendor-reported cost is recorded as `vendor_reported_cost` in meta, never billed from.
- Key path: `~/robot-factory/secrets/perplexity.key` (Dan created it 2026-11-01, `chmod 600`; never an env var). See `secrets/README.md`.
- Endpoint: `https://api.perplexity.ai/v1/responses` (Responses shape; the classic /chat/completions path is RETIRED — vendor 403 agent_api_migration_required, smoke 020).
- Model: `perplexity/sonar` (probe-proven in task 021; bare `sonar` is rejected by the new endpoint).
- Prices: input $1.00, output $2.50 per Mtok, per-call $0.005; **RATIFIED** (cover-both set, Dan 2026-11-01: vendor-reported probe costs imply ~$0.25/~$2.50 with no fee; the ratified set takes the higher figure from each pair so the ledger can only overstate).
- Adapter: `seats/perplexity.sh` -> `seats/responses_seat.py` (word-only, no tools, SCOPE: build widens nothing).

## Declared strengths (claims, not proven)
- Claim (vendor): answers grounded in live web search, with citations.

## Proven strengths
- Live calls answered through the responses adapter in task 021's probes (2 of 3 probes HTTP 200; the third pinned the model-name correction). Observed live behaviour: a source link arrived INLINE in the answer text; no separate citations/search fields appeared. Full seat smoke: 022, pending at this card's update.
