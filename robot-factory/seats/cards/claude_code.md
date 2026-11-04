# Role card: claude_code (v1, task 012, 2026-11-01)

Seat id `claude_code`, ledger seat `claude-code`, adapter `seats/claude_code.sh`.
Billing class: **subscription**, metered in **USD** (the CLI states a dollar figure, notional list price on the subscription). Status: active.

## Declared strengths
- Multi-step build work with tools (queue mode, SCOPE: build).
- Long documents and design drafts.
- Merging critique into a revised artifact (session drafter and merger).

## Proven strengths (from the scribe records, records/*.md)
- 008-maps-gate-pack: drafted the maps gate pack. Attempt 1 died at the 8000-token output cap; attempt 2 (cap 32000) exit ok, $2.6701.
- 009-phase3-local-seat-and-scribe: built the local seat adapter and scribe v1, exit ok, $2.7475.
- 009b-phase3-bookkeeping-repair: reconciled the ledger and hardened the runner, exit ok, $3.3729.
- 011s1-number5-explainer: drafter and merger in a Factory session (3 calls, each about $0.05 to $0.09). The merger accepted 4 and rejected 12 critic points, giving a written reason for each rejection.

## Turn profile
- Queue: one long agent run, from tens of thousands to millions of input tokens (cache reads), with output up to 32000 per request.
- Session (word-only): about 3k to 5k in and 1.5k to 2.7k out per call, about 20 s.
