# Record: 009b-phase3-bookkeeping-repair

*Assembled by bin/scribe.py on 2026-10-31T19:50:43-05:00 from done/, logs/, work/ and ledger.jsonl.*

## 1. Commission

From `done/009b-phase3-bookkeeping-repair.md`, verbatim:

```markdown
# Task 009b — Phase 3 bookkeeping repair (reconcile 009, protect the runner)

Framed by Alex (moderator) under Dan's Phase 3 commission (task 009),
after Alex's review of 009. The build in 009 is good; its bookkeeping
is not. This task repairs the bookkeeping and removes the two failure
modes the 009 run exposed. Nothing here is a rebuild.

SCOPE: build

## What happened in 009 (verified by Alex, for your context)

- All deliverables landed and both suites pass (phase2 35/0,
  phase3 56/0, moderator re-run). The 008 scribe record is
  verbatim-accurate and its note is genuinely the local seat's work.
- The runner died with a bash syntax error AFTER your session ended:
  you had edited run-next.sh in place while the parent bash was
  executing it, and its next read hit shifted bytes. Consequence:
  009's ACTUAL ledger line was never written. ledger.jsonl holds
  only the planned line (call_id
  009-phase3-local-seat-and-scribe@2026-10-31T19:19:59-05:00).
- At 19:30:51 a local-seat invocation in the real tree overwrote
  logs/009.meta.json (task-name-only naming; the Phase 1 paper cut),
  so the claude run's own meta is gone. That invocation also passed
  --max-out-tokens 32000 to qwen_local.sh, which refused it exactly
  as designed (adapter design choice 8 in your result). The refusal
  was correct behavior; the meta loss is the defect.

## Deliverables

D1. **Reconcile 009's actual ledger line.** Recover the claude-code
session usage for the 009 call from the CLI's own session records
(the method task 005 used for the Phase 1 backfill) and append ONE
actual line for call_id
009-phase3-local-seat-and-scribe@2026-10-31T19:19:59-05:00 in the
standing shape, with a field marking it reconciled (your choice of
key; state it in the result) and the source session file named in
your result report. If exact figures cannot be recovered, append
nothing and report that plainly. Never estimate a ledger figure.

D2. **Per-call meta naming.** Meta files (and any per-call logs your
code writes) must include the call's timestamp/call_id in their
names, for both seats' paths, so no later invocation can overwrite
an earlier call's meta. A "latest" convenience pointer is allowed
only if it cannot destroy per-call files.

D3. **Runner self-protection.** run-next.sh must re-execute from a
private copy of itself at startup (or an equivalent mechanism you
defend in the result), so a seat editing run-next.sh mid-run cannot
corrupt the executing script. Note the constraint this creates for
your own work on this task: budget.py edits are safe in place (it is
invoked per-run as a fresh process); run-next.sh edits are exactly
the hazard D3 removes, so sequence your edits and tests accordingly.

D4. **QUEUE.md alignment.** Document: the meta-naming convention
(D2), the runner self-copy behavior (D3), and reconcile QUEUE.md's
result-file promises with actual practice (results live in work/,
records in records/ — fix any stale text that says otherwise).

## Pass marks (Alex reviews)

P1. ledger.jsonl gains exactly one line (the D1 actual); every other
round's lines byte-identical to before (Alex will diff); the
appended figures trace to the session file named in your result.
P2. Sandbox proof for D2: two invocations under one task name leave
both per-call metas on disk (new phase3-style test).
P3. Sandbox proof for D3: a run whose seat edits run-next.sh mid-run
still completes and writes its actual line, or an equivalent
structural demonstration you defend.
P4. Suites: phase2 still 35 pass / 0 fail; phase3 grows (no test
silently removed); budget.yaml untouched; bash -n clean on
run-next.sh and seats/qwen_local.sh.
P5. Your result names every design choice, and your own cost stays
inside the standing $10 Factory session cap.

## Constraints

- Backups before editing run-next.sh or bin/budget.py.
- Do not touch the live laya-qwen service, Ollama, or budget.yaml.
- The scribe is not in scope except as a reader of the conventions
  you document.
- Stop-and-report beats forced completion, as always.
```

## 2. What ran

### Attempt 1: `009b-phase3-bookkeeping-repair@2026-10-31T19:38:37-05:00`

- Planned 2026-10-31T19:38:37-05:00 on seat `claude-code`: worst case $10.00, output cap 32000 tokens.
- Ran to 2026-10-31T19:49:41-05:00: exit `ok`, model `claude-opus-5-5`, 2666946 in / 66866 out tokens, cost $3.3729 (cli-reported).
- Meta `logs/009b.meta.json`: started 2026-10-31T19:38:37-05:00, finished 2026-10-31T19:49:41-05:00, exit `ok`.

Attempts: 1. Total recorded cost: $3.3729.
Logs: `logs/009b-phase3-bookkeeping-repair.log`.

## 3. Deliverables

| File | Bytes | sha256 |
|---|---|---|
| `work/009b-phase3-result.md` | 12214 | `39e903ee52976b513197dfd720663706db75211bfec908d03fd7eef11560b3a0` |

The seat's report, from `logs/009b-phase3-bookkeeping-repair.log` (verbatim):

```
preflight: PLAN 009b-phase3-bookkeeping-repair@2026-10-31T19:38:37-05:00 9.00 10.00 32000 100000 claude-code
scope: build (factory tree + usage records added, Bash allowed)
I've finished 009b, and all pass marks P1–P5 are met. The write-up is in `work/009b-phase3-result.md`.

- **P1, the 009 ledger line:** I added exactly one actual line for 009, from its session record (`22e824d6-….jsonl`): 1,844,864 tokens in, 61,104 out, cost $2.7474574. Every earlier line is byte-for-byte unchanged. The line is marked `"reconciled":true` with a `"source"` field naming the session file, following 005's convention. 009's own result had said about $2.6.
- **P2, per-call files:** each run now gets its own `logs/<name>@<stamp>.meta.json` and `.log`. If the stamp is taken, the runner waits a second and retries, and gives up with exit 4 after 5 tries. The "latest" view is `logs/<name>.log`, which is now append-only and never truncated. Both seat scripts refuse an existing or symlinked `--meta` path before any model call. A test runs the same task twice in a row and both metas survive.
- **P3, runner self-copy:** `run-next.sh` now re-runs itself from a private temp copy. In a test, a seat edits `run-next.sh` in place mid-run, the way 009 did. The run still finishes and writes its actual line. The same test against the old runner reproduces 009's corruption.
- **P4, tests:**
  - phase2 is still 35 pass / 0 fail.
  - phase3 is 71 pass / 0 fail, up from 56.
  - `bash -n` is clean on `run-next.sh` and both seat scripts.
  - `budget.yaml` is unchanged.
  - I made backups before every edit.
  - I didn't touch laya-qwen or Ollama, and didn't run `live.sh`.
- **P5, cost and design choices:** about $3.3 of the $9 budget. The result lists each design choice for ratification.
- **D4, QUEUE.md:** it now documents the per-call naming and the self-copy, and the stale text about where result files live is fixed.

**Decisions and risks for Dan:**
- **The `"exit":"ok"` on 009's line is my call.** No exit code was ever recorded for 009, so "ok" rests on its session record: a normal finish and no errors. The alternative is `"exit":"unrecorded"`.
- **This session nearly hit 009's bug itself.** I had edited `seats/claude_code.sh` in place while this session's own copy of it was still running. I put the original bytes back into that file and then installed the new version with `mv`, so the running copy kept its original text and this run should close normally.
- **The self-copy protects only `run-next.sh`.** The seat scripts are still read as they run, so for now they must be installed by `mv`, never edited in place. Giving them a self-copy too is a possible follow-up.
- **This run's own files use the old names** (`logs/009b.meta.json`), because the old runner started it. The new naming applies from the next run.
- **009's task file is still in `working/`.** That runner died before moving it to `done/`; I left it for Dan or Alex.
- **The scribe doesn't list the new `@`-stamped files.** It still reads `logs/<task>.log`, which works.

While checking, I found the result said the call-time argument to `budget.py preflight` was the 5th. It's the 4th, after `preflight`, as QUEUE.md says; I corrected the result. No staged or temp files are left over.
ledger: appended (logs/009b.meta.json, $3.3728789999999993 cli-reported, worst case $10.00)
exit=0 2026-10-31T19:49:41-05:00
```

## 4. Ledger

The 2 lines of `ledger.jsonl` with round `009b-phase3-bookkeeping-repair`, verbatim, in ledger order:

```jsonl
{"t":"2026-10-31T19:38:37-05:00","round":"009b-phase3-bookkeeping-repair","seat":"claude-code","phase":"planned","worst_usd":10.0,"spent_before_usd":24.985187,"call_id":"009b-phase3-bookkeeping-repair@2026-10-31T19:38:37-05:00","cap_usd":10.0,"cli_budget_usd":9.0,"reserve_usd":1.0,"ceiling_usd":50.0,"month":"2026-10","open_planned":1,"est_prompt_tokens":1347,"max_out_tokens":32000,"approval":null}
{"t":"2026-10-31T19:49:41-05:00","round":"009b-phase3-bookkeeping-repair","seat":"claude-code","phase":"actual","in_tokens":2666946,"out_tokens":66866,"cost_usd":3.3728789999999993,"cost_source":"cli-reported","model":"claude-opus-5-5","exit":"ok","meta":"logs/009b.meta.json","call_id":"009b-phase3-bookkeeping-repair@2026-10-31T19:38:37-05:00","worst_usd":10.0}
```

## 5. Pass marks and moderator review

The pass marks as commissioned (quoted from part 1):

```
## Pass marks (Alex reviews)

P1. ledger.jsonl gains exactly one line (the D1 actual); every other
round's lines byte-identical to before (Alex will diff); the
appended figures trace to the session file named in your result.
P2. Sandbox proof for D2: two invocations under one task name leave
both per-call metas on disk (new phase3-style test).
P3. Sandbox proof for D3: a run whose seat edits run-next.sh mid-run
still completes and writes its actual line, or an equivalent
structural demonstration you defend.
P4. Suites: phase2 still 35 pass / 0 fail; phase3 grows (no test
silently removed); budget.yaml untouched; bash -n clean on
run-next.sh and seats/qwen_local.sh.
P5. Your result names every design choice, and your own cost stays
inside the standing $10 Factory session cap.

```

**PENDING MODERATOR REVIEW.** The scribe does not judge pass marks.

## 6. Scribe's note

Task 009b-phase3-bookkeeping-repair was commissioned to repair bookkeeping defects in task 009, specifically reconciling its ledger line, implementing per-call meta naming to prevent overwrites, adding runner self-protection against mid-run edits, and aligning QUEUE.md documentation. The task executed in a single attempt on the claude-code seat, running from 2026-10-31T19:38:37-05:00 to 2026-10-31T19:49:41-05:00. The session utilized the claude-opus-5-5 model, consuming 2,666,946 input tokens and 66,866 output tokens, resulting in a recorded cost of $3.3729. The run exited with status ok. Deliverables included the file work/009b-phase3-result.md (12,214 bytes, sha256: 39e903ee52976b513197dfd720663706db75211bfec908d03fd7eef11560b3a0). The seat report confirms that the 009 ledger line was reconciled using session records, per-call meta naming was implemented with append-only logs, and run-next.sh was modified to execute from a private copy. Test suites passed with phase2 at 35/0 and phase3 at 71/0. Budget.yaml remained untouched, and no live services were affected. The result document details design choices, including the use of "ok" exit status for the reconciled 009 line and the limitation that seat scripts still require mv installation rather than in-place editing.

*Drafted by the local seat `qwen-local` (model `qwen3.6:27b`, temperature 0.2, seed 9) through `seats/qwen_local.sh`; 2694 in / 395 out tokens, $0.00 (local-free). Prompt, reply and meta: `records/logs/009b-phase3-bookkeeping-repair.note-20261031T195034.prompt.md`, `records/logs/009b-phase3-bookkeeping-repair.note-20261031T195034.reply.md`, `records/logs/009b-phase3-bookkeeping-repair.note-20261031T195034.meta.json`.*

---

A record, not an endorsement. The scribe holds no vote.
