# Jev question templates (task 016b, 2026-11-01)

Jev (TypeSafe SystemOne, seat `jev`) answers **typed questions** about a
**state** you give it. It is a certainty auditor: it flags doubt and never
grants the verified stamp. These templates are data; `bin/jev_ask.py` renders
one into an ordinary queue task:

    bin/jev_ask.py --template claim-support \
        --slot question="..." --slot answer="..." --slot evidence=@path/to/excerpt.txt \
        --out queue/NNN-jev-claim-check.md

`--slot key=@file` reads the value from a file (UTF-8). An unknown template,
a missing required slot, an unknown slot, or an existing `--out` is refused.
The rendered task carries `SEAT: jev` and one JEV block, last in the file.

| template | asks | tripwire / threshold |
|---|---|---|
| claim-support | Noul "the evidence fully supports the answer" + Score "confidence the answer is correct given only this evidence" | Noul < 0.50 |
| critique-point | Score "this point identifies a real defect in the artifact" | normalized position (score / (n-1)) >= 0.60 = act |
| position-support | Score "evidential support for this position given the state" + Noul "contradicts the agreed record" (only with `record`) | support < 0.50 flag; contradiction >= 0.50 stop |
| draft-agreement | Noul "the drafts agree in substance on the central claim" + Score "strength of the agreement" (2-5 drafts) | Noul < 0.50 = arbitrate |

## The JEV block (what the adapter accepts)

    JEV-STATE:
    <free text>

    JEV-QUESTIONS:
    - Noul: <claim>
    - Score: <quantity> | <lowest level> | ... | <highest level>
    - Choice: <question> | <option> | <option> [| ...]

- Noul: one claim, no `|`. Answer = probability the claim holds (0..1).
- Score: 2..10 levels, lowest first. Answer = a NUMBER on the continuous scale
  0 (lowest level) .. n-1 (highest level), not a level index (live, task 019:
  3.95 of 4). The adapter reports it as e.g. "3.95 of 4 — between High and
  Complete, near Complete", plus the nearest level and the **normalized
  position** `score / (n-1)` (0 = lowest, 1 = highest). If probabilities come
  back it also reports a probability-weighted position `sum_i p_i * i / (n-1)`
  as a cross-check; thresholds read the normalized position.
- Choice: 2..255 options; each option text is both the criteria key and its
  description. Answer = the option picked and its probability.
- Refused before any call (exit 3): no state, no questions, an unknown kind, a
  Choice with < 2 options, a Score with < 2 levels, empty or duplicate fields.
- Size guard: state + questions over ~30,000 estimated tokens is refused
  before any call. The vendor limit is disputed in the docs (64K vs ~32K), so
  the guard sits under the lower figure.

## Jev's known failure modes (encoded in every template's state rules)

1. **Single-claim questions only.** A compound claim gets one muddled number.
2. **Evidence trimmed to what is relevant.** Padding dilutes the judgement.
3. **No counting questions.** Jev does not count reliably.
4. **No date arithmetic.** Precompute intervals and put the result in the state.
5. **No indirect phrasing.** Negated, reported or hedged claims invert or blur.

## Template file format

Each `<name>.md` has `SLOTS:` (required), `OPTIONAL:` (may be empty),
PURPOSE / CALLER / THRESHOLDS lines, state-assembly rules, a reading guide,
and one fenced ```` ```jev ```` block. In the block, `{slot}` is replaced by
the slot value; a line starting `[if slot]` is kept (without the marker) only
when that optional slot was given. A slot used in a question line must be one
line with no `|`; no slot value may contain a `JEV-STATE:` or
`JEV-QUESTIONS:` line.

## Billing

Reported usage x registry prices (normal path). If a reply carries no usable
usage: **MODERATOR'S RULE** - tokens are recorded as null (never guessed),
`cost_source` is `unreported-billed-at-worst-case`, and the call is billed at
the planned pre-flight worst case. `bin/budget.py` accepts that only for seat
`jev`.
