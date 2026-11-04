# Role card: Jev (`jev`, api seat; task 014, adapter task 016b, 2026-11-01)

**Status: active.** The systemone adapter shipped (tasks 016b-016d) and the seat was flipped active by the moderator 2026-11-01 after the 016d review; prices ratified by Dan 2026-11-01. (Status refreshed 2026-11-03 from the ratified registry.)

- Role: **certainty auditor**. Jev **never grants the verified stamp**. Its numbers feed a human or a proven seat; they are never a verification.
- Vendor: TypeSafe SystemOne. It answers **typed questions** (Noul / Score / Choice) about a **state**. It does not chat.
- Task interface: the task must end with one block. Templates: `templates/jev/`, rendered by `bin/jev_ask.py`.

      JEV-STATE:
      <evidence, trimmed>
      JEV-QUESTIONS:
      - Noul: <one claim>
      - Score: <quantity> | <lowest> | ... | <highest>
      - Choice: <question> | <option> | <option> ...

- Known failure modes (keep questions inside them): single claims only, trimmed evidence, no counting, no date arithmetic, no indirect phrasing.
- Billing: **api** (real dollars, counted against `api_monthly_ceiling_usd`).
- Meter: reported `usage` x registry prices. If a reply carries no usable usage, the **MODERATOR'S RULE** applies: tokens are recorded null (never guessed), `cost_source` is `unreported-billed-at-worst-case`, and the call is billed at the planned worst case. `bin/budget.py` accepts that rule for `jev` only.
- Key path: `~/robot-factory/secrets/jev.key`. Mode 600, owned by Dan, a regular file (not a symlink), one line. Never an env var.
- Endpoint: `https://api.typesafe.ai/v1/systemone`, POST, Bearer auth. Shape `systemone`, PROBED live 2026-11-01 (task 016b probe 3, HTTP 200).
- Model: `jev-latest` requested; the probe resolved it to `jev-1.14.0` (recorded per call from the reply).
- Prices: input $0.042 / Mtok, output $0.0 / Mtok. **RATIFIED** by Dan 2026-11-01. Probe 3 cost 284 tokens in, 21 out: about $0.000012.
- Size guard: state + questions over ~30,000 estimated tokens is refused before any call. The docs disagree on the limit (64K vs ~32K); the guard sits under the lower figure.
- Adapter: `seats/jev.sh` -> `seats/jev_systemone.py` (stdlib, https only, no redirects, no proxies, 300 s timeout).
- Observed live: Noul (probe 3) and Score (task 019: a 5-level Score answered with the number 3.95 on the 0..4 scale; adopted by 016c). UNVERIFIED: the choice answer shape is DOCUMENTED but not yet observed live.

## Declared strengths (claims, not proven)
- Claim (UNVERIFIED): useful as a second-opinion auditor of how certain a claim is.

## Proven strengths
- Wire format and all three question kinds proven live: probe 3 (2026-11-01, Noul 0.92) proved the wire; smokes 019/019b/019c exercised Noul, Score and Choice live, and the two representation surprises they surfaced (fractional Score positions, legend as an object) are now handled by the adapter (tasks 016c/016d). That proves the instrument answers in its documented shapes; the quality of its judgement remains exactly what its doctrine says it is: a probability reading, never a stamp.
