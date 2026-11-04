# Record: 008-maps-gate-pack

*Assembled by bin/scribe.py on 2026-10-31T19:29:35-05:00 from done/, logs/, work/ and ledger.jsonl.*

## 1. Commission

From `done/008-maps-gate-pack.md`, verbatim:

```markdown
# 008: Draft the maps-shelf gate pack (design + benchmark + pass marks)

## Context
Johnny 5 gains one shelf at a time, each behind its own gate, in the
order Dan set after the Oct 30 Wikipedia gate: maps first, then code,
the action shelf last. The Wikipedia gate is the pattern: 397
held-out questions across kinds, pass marks written before the run,
labelled probes never counted as gate results, the new corpus had to
win the structured questions without losing the prose ones.

The maps shelf does not exist yet. Before anyone builds it, the gate
needs its pack, drafted in advance so the pass marks exist before
there is anything to pass. That drafting is this task. You are
writing a draft for Dan to ratify or amend; you are not building the
shelf, choosing its corpus, or running any gate.

## Deliverable (two files in work/)
1. `008-maps-gate-design.md`:
   - What the maps shelf must be able to answer when the router sends
     it a question: the question kinds it owns (for example places
     and their relations, distances, directions, administrative
     geography, coordinates), and just as explicitly what it does NOT
     own (routing and live traffic, weather, business details better
     served by other shelves).
   - The source candidates a builder could audition (open geographic
     datasets and references), each with its licensing posture and
     its known weaknesses. Candidates are proposals, not choices.
   - The gate's shape, following the Wikipedia precedent: question
     kinds with counts, how ground truth is established per kind, the
     scoring rule, and draft PASS MARKS in the house style (a margin
     to win by on the shelf's home kinds, a not-lose margin against
     the bare model on the rest), every number flagged as a proposal.
   - The traps: ambiguous place names, stale data, as-the-crow-flies
     versus road distance, places that share names across states and
     countries, and how the gate design defends against each.
2. `008-maps-benchmark-draft.md`: the draft question set itself, in
   the kinds and proportions your design proposes (aim for a set a
   real gate could run, on the order of 150 to 300 questions). Each
   question carries: the expected answer, and a verification note
   naming how a human can check that answer against an authoritative
   source (a dataset, an official listing, a reference work). Weight
   the set toward the Gulf Coast and the Pacific Northwest without
   making it parochial; Dan's life runs between Ocean Springs and
   Seattle, and a shelf that only knows home is a shelf that fails
   honestly elsewhere.

## The honesty rule for this task
You cannot browse, and a benchmark is only as good as its ground
truth. So: any answer you are not certain of gets flagged inline as
UNVERIFIED with its verification note, never smoothed over. A smaller
set of answers you stand behind beats a larger set with guesses in
it. The verification notes are not decoration; Dan or Alex will
spot-check against them before this pack can be ratified, and the
pack must say so about itself.

## Constraints
- Drafts, labelled as drafts, for Dan's ratification. No shelf is
  built, no source is chosen, no gate is run, nothing is published.
- Text work only, inside the factory tree. No network, no installs.
- Do not touch the runner, the ledger, budget.yaml, or any other
  machinery; this task writes its two deliverables and its result
  summary only.
- Close with a short result summary in your reply: the kinds and
  counts you proposed, the pass marks you drafted, how many benchmark
  answers you flagged UNVERIFIED, and anything Dan must decide before
  the pack can be ratified.
```

## 2. What ran

### Attempt 1: `008-maps-gate-pack@2026-10-31T13:14:27-05:00`

- Planned 2026-10-31T13:14:27-05:00 on seat `claude-code`: worst case $10.00, output cap 8000 tokens.
- Ran to 2026-10-31T13:26:10-05:00: exit `error`, model `claude-opus-5-5`, 546323 in / 69651 out tokens, cost $1.9515 (cli-reported).
- Meta `logs/008.meta.json`: started 2026-10-31T13:14:27-05:00, finished 2026-10-31T13:26:10-05:00, exit `error`.

### Attempt 2: `008-maps-gate-pack@2026-10-31T13:58:36-05:00`

- Planned 2026-10-31T13:58:36-05:00 on seat `claude-code`: worst case $10.00, output cap 32000 tokens.
- Ran to 2026-10-31T14:12:18-05:00: exit `ok`, model `claude-opus-5-5`, 616597 in / 91437 out tokens, cost $2.6701 (cli-reported).
- Meta `logs/008-maps-gate-pack.meta.json`: started 2026-10-31T13:58:36-05:00, finished 2026-10-31T14:12:18-05:00, exit `ok`.

Attempts: 2. Total recorded cost: $4.6216.
Logs: `logs/008-maps-gate-pack.attempt1.log`, `logs/008-maps-gate-pack.log`.

## 3. Deliverables

| File | Bytes | sha256 |
|---|---|---|
| `work/008-maps-benchmark-draft.md` | 27307 | `62f9e0d9cfbf700d20e54ff22c265d3eddc7403152573c9ad38cab01e8fdb831` |
| `work/008-maps-gate-design.md` | 13481 | `ccdfcd3a073369d4cdc54571a4aa9574c39ad48a27d994bd58dce8a0f583fb89` |

The seat's report, from `logs/008-maps-gate-pack.log` (verbatim):

```
preflight: PLAN 008-maps-gate-pack@2026-10-31T13:58:36-05:00 9.00 10.00 32000 100000
I've drafted the maps-shelf gate pack for you to ratify or amend. There are two files in `work/`: `008-maps-gate-design.md` and `008-maps-benchmark-draft.md`. Both are labelled as drafts. I didn't build anything, choose a source, run anything or publish anything, and I didn't touch the runner, the ledger or `budget.yaml`.

I wrote the benchmark from memory, with no network access and no script run. You or Alex need to spot-check it against its verification notes before it can be ratified; the pack says so in both files and includes a sign-off table. I counted the questions per kind with grep and the counts match the table below.

**Kinds and counts (201 questions):**

| Kind | Questions | Stratum |
|---|---:|---|
| A. County, parish or state a place is in | 50 | home |
| B. Places that share a name (Jackson, Portland, Columbia, Springfield, Georgia…) | 24 | home |
| C. Borders, neighbouring counties, water bodies, state high points, time zones | 30 | home |
| D. Coordinates for a place, and the place at given coordinates | 20 | home |
| E. Straight-line distance | 16 | home |
| F. Direction (which way, which is farther north or west) | 14 | home |
| G. Renamed places and features | 12 | home |
| H. Questions the shelf must decline (live traffic, weather, business details, schedules) | 15 | abstain |
| I. Questions the Wikipedia shelf already owns | 20 | control |

About 45% of the questions are Gulf Coast, 30% Pacific Northwest, and the rest elsewhere in the US and the world.

**Draft pass marks (all proposals):**
- **Home (A–G pooled, 166 questions):** the maps shelf must score at least 3 points above the comparator.
- **Control (20 questions):** it may be no more than 2 points below the comparator.
- **Abstain (15 questions):** it must do no worse than the comparator and get at least 14 of 15 right. I added that fixed floor because 2 points of 15 questions is less than one question.
- **Ties:** within 1 point of a threshold is a tie, and a tie keeps the current system.
- **Per-kind results** are reported for information only, not pass/fail, because each kind is too small for a 3-point margin to mean anything.

**UNVERIFIED answers: 20, plus one note that isn't graded.**
- **All 16 distances:** I computed them by hand because the script was blocked, so nothing is machine-checked. Each should be recomputed from Census coordinates.
- **Columbia, MS** being in Marion County.
- **Three Wikipedia-side facts:** Seattle's 2020 population, Biloxi's years as French capital, and the year Gulf Islands National Seashore was set up.
- **The ungraded note:** the year the Biloxi Bay bridge reopened.

I left out questions I couldn't stand behind rather than guess.

**Decisions for you before ratification:**
1. **Road distance:** this task excludes routing, but the harness plan includes an OSRM/Valhalla route tool. The draft treats road distance as not owned. One question (H12) changes if you decide the shelf owns static road distance.
2. **Comparator:** the draft compares against the current live system (model plus Wikipedia shelf), with the bare model reported for reference. Use the bare model instead if that's what "not-lose against the bare model" meant.
3. **Pass marks:** whether the control set grows from 20 to about 50, since at 20 questions the 2-point rule means losing even one question fails.
4. **Tolerances:** ±0.15° for coordinates, ±5% or ±5 km for distances, and a 10° margin rule for directions.
5. **Renamed features:** the draft accepts either name for Gulf of America / Gulf of Mexico and Mount McKinley / Denali.
6. **Ambiguous names:** whether a single unqualified answer to a question like "What county is Jackson in?" is graded incorrect.
7. **Sources:** which sources are used to build the shelf and which are held back as ground truth.
8. **Spot-check:** you or Alex, with the UNVERIFIED items first.
ledger: appended (logs/008-maps-gate-pack.meta.json, $2.6701078000000003 cli-reported, worst case $10.00)
exit=0 2026-10-31T14:12:18-05:00
```

## 4. Ledger

The 4 lines of `ledger.jsonl` with round `008-maps-gate-pack`, verbatim, in ledger order:

```jsonl
{"t":"2026-10-31T13:14:27-05:00","round":"008-maps-gate-pack","seat":"claude-code","phase":"planned","worst_usd":10.0,"spent_before_usd":10.363556,"call_id":"008-maps-gate-pack@2026-10-31T13:14:27-05:00","cap_usd":10.0,"cli_budget_usd":9.0,"reserve_usd":1.0,"ceiling_usd":50.0,"month":"2026-10","open_planned":0,"est_prompt_tokens":1226,"max_out_tokens":8000,"approval":null}
{"t":"2026-10-31T13:26:10-05:00","round":"008-maps-gate-pack","seat":"claude-code","phase":"actual","in_tokens":546323,"out_tokens":69651,"cost_usd":1.9515225999999999,"cost_source":"cli-reported","model":"claude-opus-5-5","exit":"error","meta":"logs/008.meta.json","call_id":"008-maps-gate-pack@2026-10-31T13:14:27-05:00","worst_usd":10.0}
{"t":"2026-10-31T13:58:36-05:00","round":"008-maps-gate-pack","seat":"claude-code","phase":"planned","worst_usd":10.0,"spent_before_usd":12.315079,"call_id":"008-maps-gate-pack@2026-10-31T13:58:36-05:00","cap_usd":10.0,"cli_budget_usd":9.0,"reserve_usd":1.0,"ceiling_usd":50.0,"month":"2026-10","open_planned":0,"est_prompt_tokens":1226,"max_out_tokens":32000,"approval":null}
{"t":"2026-10-31T14:12:18-05:00","round":"008-maps-gate-pack","seat":"claude-code","phase":"actual","in_tokens":616597,"out_tokens":91437,"cost_usd":2.6701078000000003,"cost_source":"cli-reported","model":"claude-opus-5-5","exit":"ok","meta":"logs/008-maps-gate-pack.meta.json","call_id":"008-maps-gate-pack@2026-10-31T13:58:36-05:00","worst_usd":10.0}
```

## 5. Pass marks and moderator review

The commission names no pass-marks section; see part 1.

**PENDING MODERATOR REVIEW.** The scribe does not judge pass marks.

## 6. Scribe's note

Task 008 commissioned the drafting of the maps-shelf gate pack, including design specifications and a benchmark question set, to establish pass marks before shelf construction. Two attempts were executed on the claude-code seat using the claude-opus-5-5 model. The first attempt exited with an error, while the second completed successfully. The total recorded cost for both attempts was $4.6216. The deliverables are two draft files in the work directory: 008-maps-gate-design.md and 008-maps-benchmark-draft.md. The benchmark contains 201 questions across nine kinds, weighted toward the Gulf Coast and Pacific Northwest. Draft pass marks propose a three-point margin for home kinds and a two-point tolerance for control questions. Twenty answers were flagged as UNVERIFIED, including all distance calculations and specific geographic facts, requiring manual spot-checking. The design excludes routing and live data. Decisions pending ratification include comparator selection, pass mark thresholds, coordinate tolerances, and source selection. No shelf was built, no sources chosen, and no gate was run during this task.

*Drafted by the local seat `qwen-local` (model `qwen3.6:27b`, temperature 0.2, seed 9) through `seats/qwen_local.sh`; 2875 in / 233 out tokens, $0.00 (local-free). Prompt, reply and meta: `records/logs/008-maps-gate-pack.note-20261031T192929.prompt.md`, `records/logs/008-maps-gate-pack.note-20261031T192929.reply.md`, `records/logs/008-maps-gate-pack.note-20261031T192929.meta.json`.*

---

A record, not an endorsement. The scribe holds no vote.
