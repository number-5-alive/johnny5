# Role card: DeepSeek (`deepseek`, api seat, task 014, 2026-11-01)

**Status: active.** Key provisioned by Dan 2026-11-01; prices ratified by Dan 2026-11-01; smoke 018b passed 2026-11-01. (Status refreshed 2026-11-03 from the ratified registry.)

- Role: general word seat (low-cost api candidate).
- Billing: **api** (real dollars, counted against `api_monthly_ceiling_usd`, its own tally, never added to the others).
- Meter: **tokens-priced-to-usd**: `cost_usd = in_tokens x price_in + out_tokens x price_out (+ per-call fee)`, tokens only from the vendor's reported usage; no usage = exit 4, nothing guessed.
- Key path: `~/robot-factory/secrets/deepseek.key` (Dan creates it at his own terminal, `chmod 600`; never an env var). See `secrets/README.md`.
- Endpoint: `https://api.deepseek.com` (OpenAI-compatible; confirmed 2026-11-01)
- Model: `deepseek-reasoner` (chosen by Dan 2026-11-01 over deepseek-flash for reasoning strength; the older `deepseek-chat` alias is retired)
- Prices: input $0.28, output $0.42 per Mtok. **RATIFIED** by Dan 2026-11-01 (single secondary source read 2026-11-01; the single-source caveat stands until a DeepSeek invoice or pricing page confirms).
- Adapter: `seats/deepseek.sh` -> `seats/api_seat.py` (word-only, no tools, SCOPE: build widens nothing).

## Declared strengths (claims, not proven)
- Claim (vendor, UNVERIFIED): OpenAI-compatible chat API at low per-token prices.
- Claim (vendor, UNVERIFIED): cache-hit input is billed cheaper; this seat prices every input token at the full input price (conservative).

## Proven strengths
- Live wire proven: smoke 018b passed 2026-11-01 (175 in / 222 out, $0.00014224 at reasoner rates). Note: the vendor response self-reported model "deepseek-flash" although "deepseek-reasoner" was requested; billing follows the requested model and the adapter records the vendor-reported name.
