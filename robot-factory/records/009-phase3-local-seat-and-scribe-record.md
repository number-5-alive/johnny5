# Record: 009-phase3-local-seat-and-scribe

*Assembled by bin/scribe.py on 2026-10-31T19:51:03-05:00 from done/, logs/, work/ and ledger.jsonl.*

## 1. Commission

From `done/009-phase3-local-seat-and-scribe.md`, verbatim:

```markdown
# Task 009 — Phase 3: local qwen seat + scribe v1

Commissioned by Dan (2026-10-31 evening), framed by Alex (moderator).
Factory spec 001 build order: Phase 3. You are the Claude Code seat
building the Factory's second seat and its scribe. Alex moderates and
reviews against the pass marks below; Dan commissioned and approves.

SCOPE: build

## Context you can rely on

- `~/robot-factory/seats/claude_code.sh` is the Phase 1 seat adapter
  and defines the seat contract (spec §2.2): inputs, result + meta
  outputs, ledger actual lines, fail-closed when token/cost fields
  cannot be filled. The new seat must satisfy the same contract.
- Ledger actual-line shape (from ledger.jsonl): t, round, seat,
  phase ("actual"), in_tokens, out_tokens, cost_usd, cost_source,
  model, exit, meta, call_id, worst_usd.
- `~/robot-factory/budget.yaml` already carries the local caps
  (Dan's Q4 numbers): local max_in_tokens 24000, max_out_tokens 4000.
  Do not change budget.yaml numbers.
- The local model is qwen3.6:27b served by Ollama on this machine
  (http://127.0.0.1:11434). It is the same model the live laya-qwen
  service uses. NOT qwen3-coder:30b — the scribe is Johnny, and
  Johnny is qwen3.6:27b.
- The runner (`run-next.sh` + `bin/budget.py`) currently always
  invokes the Claude seat. Phase 2 behavior (estimate, pre-flight,
  planned/refused ledger lines, approvals, caps) must not regress:
  tests/phase2 stands at 35 pass / 0 fail.

## Deliverables

D1. **Local seat adapter** at `~/robot-factory/seats/qwen_local.sh`,
satisfying the §2.2 contract against Ollama:
- POST to the local Ollama API (127.0.0.1:11434 only; no other
  network), model qwen3.6:27b, non-streaming.
- Token counts from Ollama's own response fields
  (prompt_eval_count / eval_count). Fail closed if either is absent.
- Output cap hard-enforced via num_predict = local max_out_tokens
  from budget.yaml (read at run time, like the frontier path).
- Input overage: if prompt_eval_count exceeds local max_in_tokens,
  the result still returns but the meta and ledger line must carry
  an explicit cap_exceeded flag. Never silent.
- Ledger actual lines in the standing shape with seat "qwen-local",
  cost_usd 0.0, and a cost_source literal that cannot be confused
  with "cli-reported" (suggestion: "local-free").
- Low temperature by default (records should be stable), with the
  value recorded in meta.

D2. **Seat selection in the runner**, minimal and backward
compatible: a task file may carry the exact line `SEAT: qwen_local`
(set only by Alex on Dan's commission, same discipline as the
SCOPE: line). Absent the line, the runner uses the Claude seat
exactly as today. Pre-flight for a local task must price worst-case
USD as 0 (no dollar-cap refusal for a free seat) while still
writing its planned ledger line, and token caps still apply.

D3. **Scribe v1** at `~/robot-factory/bin/scribe.py` (Python, to sit
beside budget.py). Given a completed task name, it assembles
`~/robot-factory/records/<task>-record.md` from done/<task>.md,
logs/, and that task's ledger lines, with these sections:
Commission; What ran; Deliverables; Ledger (the task's lines
verbatim); Pass marks and moderator review (write
"PENDING MODERATOR REVIEW" — the review is Alex's, never the
scribe's); Scribe's note (one short narrative paragraph); and the
standing footer: "A record, not an endorsement. The scribe holds
no vote."
- The Scribe's note paragraph is drafted by the local seat THROUGH
  the new adapter in D1 (dogfood both in one stroke).
- The scribe writes ONLY under records/ (plus its own logs). It
  never edits done/, queue/, ledger.jsonl, or any task file.

D4. **Demonstration + tests**, in the tests/phase2 style (sandbox
suite under tests/phase3/):
- One sandbox task run end-to-end through run-next.sh carrying
  `SEAT: qwen_local`, producing a done/ entry and a ledger actual
  line with cost_usd 0.0 and real token counts.
- One runaway test proving the output cap: eval_count at or under
  the configured cap on a prompt that asks for far more.
- The scribe run over task 008-maps-gate-pack, producing
  records/008-maps-gate-pack-record.md whose Ledger section matches
  ledger.jsonl exactly for that round.

## Pass marks (Alex reviews against these)

P1. D1 adapter exists, meets the contract points above, and fails
closed in a sandbox test with Ollama unreachable.
P2. D2 selection works both ways: a SEAT: qwen_local task routes
local; a task with no SEAT line still routes to the Claude seat
(evidence from pre-flight/planned lines or sandbox runs).
P3. Output cap enforced (D4 runaway test); input overage flagged,
never silent.
P4. records/008-maps-gate-pack-record.md exists, contains all six
sections plus the footer, its Ledger section is verbatim-accurate,
and its Scribe's note is attributed to the local seat.
P5. No regressions: tests/phase2 still 35 pass / 0 fail; your new
tests/phase3 suite passes; budget.yaml numbers unchanged.
P6. Your reported cost for THIS task stays inside the standing $10
Factory session cap, and your result report names every design
choice you made (the C-list discipline from task 006).

## Constraints

- Backups before editing run-next.sh or bin/budget.py (your standing
  habit; keep it).
- Do not touch the live laya-qwen service or its files, and do not
  restart Ollama. The local seat shares the GPU with the live
  service through the same Ollama instance; queueing delays are
  acceptable in v1, contention is recorded (timings in meta), never
  "fixed" by preemption.
- Localhost network only for the new seat. No new packages.
- If a contract point genuinely cannot be met, stop that part,
  report it plainly in your result, and finish the rest. A clean
  partial beats a forced whole.
```

## 2. What ran

### Attempt 1: `009-phase3-local-seat-and-scribe@2026-10-31T19:19:59-05:00`

- Planned 2026-10-31T19:19:59-05:00 on seat `claude-code`: worst case $10.00, output cap 32000 tokens.
- Ran to 2026-10-31T19:30:50-05:00: exit `ok`, model `claude-opus-5-5`, 1844864 in / 61104 out tokens, cost $2.7475 (cli-reported).
- Meta `logs/009-phase3-local-seat-and-scribe@20261031T191959-0500.meta.json`: started 2026-10-31T19:19:59-05:00, finished 2026-10-31T19:30:50-05:00, exit `ok`.

Attempts: 1. Total recorded cost: $2.7475.
Logs: `logs/009-phase3-local-seat-and-scribe.log`.

## 3. Deliverables

| File | Bytes | sha256 |
|---|---|---|
| `work/009-phase3-result.md` | 9085 | `cd1744c7c7718bff5f3a1cdfb4a6a231a7dfbd84ae437c3e4dd9bcaa9b214646` |

The seat's report, from `logs/009-phase3-local-seat-and-scribe.log` (verbatim):

```
preflight: PLAN 009-phase3-local-seat-and-scribe@2026-10-31T19:19:59-05:00 9.00 10.00 32000 100000
scope: build (factory tree + usage records added, Bash allowed)
scope: build ignored: the local seat has no tools, nothing is widened
qwen_local.sh: --max-out-tokens 32000 exceeds local.max_out_tokens 4000
```

## 4. Ledger

The 2 lines of `ledger.jsonl` with round `009-phase3-local-seat-and-scribe`, verbatim, in ledger order:

```jsonl
{"t":"2026-10-31T19:19:59-05:00","round":"009-phase3-local-seat-and-scribe","seat":"claude-code","phase":"planned","worst_usd":10.0,"spent_before_usd":14.985187,"call_id":"009-phase3-local-seat-and-scribe@2026-10-31T19:19:59-05:00","cap_usd":10.0,"cli_budget_usd":9.0,"reserve_usd":1.0,"ceiling_usd":50.0,"month":"2026-10","open_planned":0,"est_prompt_tokens":1913,"max_out_tokens":32000,"approval":null}
{"t":"2026-10-31T19:30:50-05:00","round":"009-phase3-local-seat-and-scribe","seat":"claude-code","phase":"actual","in_tokens":1844864,"out_tokens":61104,"cost_usd":2.7474574,"cost_source":"cli-reported","model":"claude-opus-5-5","exit":"ok","meta":"logs/009-phase3-local-seat-and-scribe@20261031T191959-0500.meta.json","call_id":"009-phase3-local-seat-and-scribe@2026-10-31T19:19:59-05:00","worst_usd":10.0,"reconciled":true,"source":"~/.claude/projects/-home-peacekins-robot-factory-work/22e824d6-1ee6-41b5-95d6-c3bb892f0bc7.jsonl"}
```

## 5. Pass marks and moderator review

The pass marks as commissioned (quoted from part 1):

```
## Pass marks (Alex reviews against these)

P1. D1 adapter exists, meets the contract points above, and fails
closed in a sandbox test with Ollama unreachable.
P2. D2 selection works both ways: a SEAT: qwen_local task routes
local; a task with no SEAT line still routes to the Claude seat
(evidence from pre-flight/planned lines or sandbox runs).
P3. Output cap enforced (D4 runaway test); input overage flagged,
never silent.
P4. records/008-maps-gate-pack-record.md exists, contains all six
sections plus the footer, its Ledger section is verbatim-accurate,
and its Scribe's note is attributed to the local seat.
P5. No regressions: tests/phase2 still 35 pass / 0 fail; your new
tests/phase3 suite passes; budget.yaml numbers unchanged.
P6. Your reported cost for THIS task stays inside the standing $10
Factory session cap, and your result report names every design
choice you made (the C-list discipline from task 006).

```

**PENDING MODERATOR REVIEW.** The scribe does not judge pass marks.

## 6. Scribe's note

Task 009-phase3-local-seat-and-scribe was commissioned by Dan on 2026-10-31 evening and framed by Alex to build the Factory’s second seat adapter and a scribe utility. The scope required creating a local Qwen seat adapter at `seats/qwen_local.sh`, implementing seat selection logic in the runner, developing a Python scribe at `bin/scribe.py`, and providing demonstration tests. One attempt was executed on the `claude-code` seat using model `claude-opus-5-5`. The run started at 2026-10-31T19:19:59-05:00 and exited with status `ok` at 2026-10-31T19:30:50-05:00. It consumed 1,844,864 input tokens and 61,104 output tokens, resulting in a recorded cost of $2.7475 via cli-reported source. The total recorded cost for the task is $2.7475. The primary deliverable is the result report file `work/009-phase3-result.md` (9085 bytes, sha256: cd1744c7c7718bff5f3a1cdfb4a6a231a7dfbd84ae437c3e4dd9bcaa9b214646). Logs indicate a preflight plan with a worst-case estimate of $9.00 against a $10.00 cap, and noted that the local seat adapter configuration exceeded the defined local maximum output tokens of 4000.

*Drafted by the local seat `qwen-local` (model `qwen3.6:27b`, temperature 0.2, seed 9) through `seats/qwen_local.sh`; 2269 in / 375 out tokens, $0.00 (local-free). Prompt, reply and meta: `records/logs/009-phase3-local-seat-and-scribe.note-20261031T195055.prompt.md`, `records/logs/009-phase3-local-seat-and-scribe.note-20261031T195055.reply.md`, `records/logs/009-phase3-local-seat-and-scribe.note-20261031T195055.meta.json`.*

---

A record, not an endorsement. The scribe holds no vote.
