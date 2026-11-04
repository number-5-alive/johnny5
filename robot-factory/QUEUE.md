# Robot Factory queue (v0, 2026-10-31)

The wire between Alex and the Claude Code seat on argo. Dan directs;
Alex posts tasks; the seat works them; results come back as files.
Dan never hand-carries a prompt.

## Layout
- queue/    task files waiting (markdown, named NNN-short-title.md)
- working/  the task the seat is on right now
- done/     finished task files (the task text only; no results here)
- logs/     per-call logs and metas, plus one append-only log per task
            (see "Per-call files" below)
- work/     the seat's working directory: artifacts and result files
            (NNN-*-result.md) land here
- records/  the scribe's records of finished tasks (NNN-*-record.md)

## Task file shape
# Title
## Context      (only what the seat needs; it cannot see Alex's chat)
## Deliverable  (the file(s) to produce in work/, named exactly)
## Constraints  (scope, tools, what NOT to touch)

## Rules
- The seat works ONLY inside ~/robot-factory/work unless a task says otherwise.
- A task is one deliverable. Big work is several tasks.
- Results are drafts for Dan's review. Nothing leaves argo on a result alone.

## Scope marker
A task file containing the exact line `SCOPE: build` runs widened:
the factory tree and ~/.claude/projects are added to the seat's
access and Bash is pre-approved, so build tasks can install and
verify their own work. Tasks without the marker run confined to
work/, as before. The marker is set by whoever writes the task
(Alex, on Dan's commission), never by the seat itself.

## Phase 1: seat adapter and ledger (2026-10-31)
Every queue run now goes through seats/claude_code.sh (queue mode).
It makes the same call v0 made, with JSON output, so each run's
reply, tokens and cost come back as data. The reply still lands in
the log as before.

- meta file           one per run: seat, model, started, finished,
                       in_tokens, out_tokens, cost_usd, cost_source,
                       exit. Never overwritten. (Phase 1 named it
                       logs/NNN.meta.json; since 009b it is per-call,
                       see "Per-call files" below.)
- ledger.jsonl         one "actual" line per run, appended, never
                       edited. Lines marked "backfilled" were rebuilt
                       from ~/.claude/projects after the fact.

Costs are the CLI's own figures (cost_source "cli-reported"). On the
subscription they are list-price figures, recorded as reported, and
nothing is enforced. If model, tokens or cost can't be filled, the
run writes no ledger line, its log says so, and run-next.sh exits 4.
The adapter also has a text mode (all tools off) for the convening
loop. The queue doesn't use it yet.

## Phase 2: caps, estimate, approval (2026-10-31, task 006)
Every queue run now passes a pre-flight (bin/budget.py) before any
model call. The numbers live in budget.yaml (Dan's Q3/Q4 rulings) and
are read at run time.

- Effective cap: the Factory session cap ($10) by default. A task may
  LOWER its cap with a line `CAP_USD: 2.50`. A HIGHER cap needs Dan's
  approval. A line `APPROVAL: required` asks for approval whatever the cap.
- Worst case = the effective cap. The CLI gets `--max-budget-usd` of
  (cap - overshoot reserve), because the CLI checks its budget after
  each request and can finish one request past it. Each request's
  output is capped at 8,000 tokens and the CLI auto-compacts at 100k.
- Before the call, ledger.jsonl gets a "planned" line (worst_usd,
  spent_before_usd = month-to-date, call_id). After the call it gets
  the "actual" line with the same call_id, exit "capped" if the CLI
  stopped it. A planned line with no actual counts at its worst case.
- Refused (no approval, hash or time mismatch, prompt over 60k-token
  estimate, cap not above the reserve, month-to-date + worst case over
  the $50 ceiling, or an unreadable budget.yaml/ledger): no model call;
  ledger gets one "refused" line with the reason; the task moves to
  held/ unchanged; its log says why; run-next.sh exits 5.

Approving (Dan only, in his own terminal):
    ~/robot-factory/approve.sh held/NNN-title.md   (or queue/NNN-title.md)
    mv held/NNN-title.md queue/                    (if it was held)
approve.sh refuses without a terminal on stdin and stdout. It records
the file's sha256 and the time in approvals/NNN-title.jsonl (appended).
The runner honours only the latest record, and only if the file still
has that hash and was not modified after it. Any edit voids the approval.

New folders: held/ (refused tasks waiting on Dan), approvals/ (approval
records), bin/ (budget.py). Runner exit codes: 0 ran, 4 ledger/meta
problem, 5 refused before any call.

## Per-call files and runner self-copy (2026-10-31, task 009b)
Task 009 edited run-next.sh while that runner was running. Bash reads a
script as it goes, so the running runner went on into the new text: the
009 log was truncated and logs/009.meta.json was overwritten. Two
conventions stop that from happening again.

Per-call naming. Every call gets one instant. The call_id is
`<name>@<date -Is>`, and both per-call files carry the same instant as
a stamp, `YYYYmmddTHHMMSS±zzzz`:
    logs/<name>@<stamp>.meta.json   this call's meta (the ledger's "meta")
    logs/<name>@<stamp>.log         this call's log; line 1 is
                                    "call: <call_id>  meta: ...  log: ..."
  e.g. call_id 931-x@2026-10-31T19:46:41-05:00 ->
       logs/931-x@20261031T194641-0500.meta.json and .log
- A second run of the same task name gets new files. Nothing is reused.
  If the stamp is taken (same name, same second), the runner waits a
  second and takes the next one. After 5 tries it refuses with exit 4,
  leaving the task in queue/.
- The per-call log is created exclusively. Each adapter refuses an
  existing --meta path (exit 3, before any model call, file untouched)
  and writes the meta with exclusive create.
- "Latest" view: logs/<name>.log is the task's cumulative log. When each
  call ends, including a refused one, its whole per-call log is appended
  there. That file is never truncated or rewritten. It is a convenience
  copy: the per-call files are the record. There are no symlinks, and no
  "latest" meta file. To find a call's meta, use the "meta" field on its
  ledger lines.
- budget.py preflight takes the call time as an optional 4th argument
  (`date -Is` format), so the planned line's call_id matches the files.
  Without it, it uses the current time as before.

Runner self-copy. At startup, run-next.sh copies itself to a private
temp file (mktemp, under $TMPDIR or /tmp) and re-executes from that copy.
A seat may edit run-next.sh mid-run, in place or by replacement. The
edit lands in the file and takes effect on the NEXT run. The current run
finishes on the copy it started with and writes its actual line. The
copy is deleted on exit. The marker variable is not passed to children,
so a runner started by a seat (a sandbox test, say) makes its own copy.
Even so, build tasks that change run-next.sh should still install it by
`mv` of a finished file, never by editing it in place.

Readers (the scribe included): logs/<name>.log keeps its name and still
holds each call's output, now appended rather than replaced. Per-call
files are named <name>@<stamp>.*. Pre-009b files (logs/NNN.meta.json,
logs/NNN-*.meta.json) are left as they are.
Runner exit codes added: 1 if the self-copy cannot be made (nothing has
run yet), and 4 if the per-call names are taken or can't be created.
