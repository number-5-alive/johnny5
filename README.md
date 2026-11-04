# Johnny 5: Number 5 Alive

Every AI you can talk to today is an oracle: one enormous model, in
someone else's data center, pretending to be best at everything, lit
up at full power whether you asked it about the universe or about a
town ten miles away. It answers to the company that runs it. Its
memory is not yours.

Johnny 5 is a project to build the opposite shape. A personal system
of composed minds: a local half that lives in your house and holds
your own shelves of checked knowledge, your records, your rules; and
an external half, a moderator with the best models in the world on
call, convened per question and cast to their strengths. One input
arrives and is decided by both halves together. Small questions die
cheap, close to home. Big ones get a room, a record, and a dissent
preserved. The human commissions the work, sets the caps, and can
read every word of the ledger.

Johnny himself is the local half, running today on a home server on
the Mississippi Gulf Coast: he checks his shelves before he answers
and labels how sure he is. Around him, the Robot Factory builds and
S.A.I.N.T. (System for Aligned Intelligence and Negotiated Truth)
deliberates, under a moderator who drafts nothing and votes on
nothing. This repository is the whole thing, code and records
together, published so the claims can be checked. What is built is
labelled built. What is vision is labelled vision.

Live project page: https://number5alive.com

## Johnny: the local half

Johnny runs a capable open model on hardware his owner holds,
checks his answers against a local library before he speaks, and
labels everything he says: verified, or guess. Most AI systems
optimize for fluency. This one optimizes for knowing when it does
not know. Abstaining is a first-class outcome here, not a failure
mode.

## The modes

The answering system has four modes, each special for a different
reason:

- **Grasshopper** (verified): the question is searched against local
  shelves first. The model then drafts the answer five times,
  independently. If at least four of the five drafts agree, the answer
  is presented as verified with its sources. If they do not agree, the
  system says so, and shows its best guess clearly labelled as a guess.
- **Butterfly** (fast): one draft, open range, quick. Useful, and
  labelled as what it is: unverified.
- **Input** (bare model): no library, no checks. The raw model, for
  comparison and for questions where evidence does not apply.
- **Hang glider** (novelty): the mode for new ideas rather than true
  ones. Described in its own section below.

The service exposes an OpenAI-compatible chat endpoint, so any client
that speaks that protocol (Open WebUI is included as an optional front
end) can sit in front of it.

## Hang glider

Hang glider exists because the rest of the system is built to
converge, and convergence is the wrong tool for finding a new idea.
It runs the bare model five times, one draft after another. Each new
draft is briefed with the directions the earlier drafts already took
and has to go somewhere else, so the panel spreads out instead of
piling onto the obvious answer.

A separate reassessment pass then reads the spread. It names the
consensus attractor, the direction the panel kept returning to, sets
it aside, and looks for the most novel combination of the spread that
is still workable: elements from different drafts that no single draft
put together. What the reader gets is a five-fold card:

1. The final draft, developed from that combination.
2. A representative conservative pass, in a collapsed section.
3. A representative middle pass, in a collapsed section.
4. A representative liberal pass, in a collapsed section.
5. The reader's own decision, which is the fifth element on purpose.

The full spread and the reassessment reasoning are kept in the run
record, one layer down, for anyone who wants to dig or overrule the
pick.

Hang glider carries no stamp of any kind: not verified, not anything
else. It is calibrated, not gated. A contract suite checks the parts
that can be checked mechanically (the card's shape, the completeness
of the record, the absence of any stamp). Its calibration sweep,
which hunts the coherence cliff above temperature 2.0, ran on
2026-11-03: coherence held at every step from 2.0 to 3.0, no cliff
found, so 3.0 stands as the working ceiling by the commissioner's
ruling. The diversity baseline from those runs (a median of 3
clusters, attractor strength 0.4) is recorded, so a future change
that quietly narrows the spread will show. There is no accuracy pass mark, by
design. Novelty does not grade that way, and pretending otherwise
would manufacture a certainty this project does not deal in.

## Measured, not promised

Every knowledge shelf joins this system by passing a gate: a held-out
question set, pass marks written before the run, and a confirm-or-revert
verdict on the result. The first full gate ran on October 30, 2026,
comparing a 2023 Wikipedia snapshot against a 2026 one across 397
held-out questions:

| Stratum | 2023 snapshot | 2026 snapshot | Margin |
| --- | --- | --- | --- |
| Table-answerable (n=197) | 23.86% | 83.76% | +59.90 |
| Prose-answerable (n=200) | 67.50% | 78.00% | +10.50 |

Verdict: CONFIRM. The live deployment has run the 2026 snapshot
(Wikipedia, October 1, 2026) since that evening, and the 2023 index is
kept untouched as the revert path. The evaluation harness that produced
these numbers ships in this repo (`src/laya_qwen/eval.py`,
`src/laya_qwen/grader.py`, `scripts/`), because a trust claim you cannot
re-run yourself is just marketing.

### The temperature ladder gate

On November 2, 2026, a pre-registered experiment asked whether
Grasshopper would do better if its five drafts were written at five
different temperatures instead of one fixed temperature. The pass
marks were written before the run, as always. The ladder's
agreed-answer accuracy came in at 93.8%, against 95.0% for the fixed
panel it was trying to replace. It missed its mark, so it was not
adopted: the live lane still drafts at one fixed temperature, and the
rainbow stays a diversity tool, not an accuracy tool.

A companion experiment failed the same week. A proposed label for
bare-model runs, which would have certified that a five-temperature
panel ran its range and converged, produced a stamped accuracy of
31.2% against a pass mark of 60%. It did not ship. The full report
ships with the project records (`robot-factory/records/`).

This section will keep growing in both directions. A failed experiment
is a result, and it gets published with the same care as a successful
one.

## Architecture

- **Shelves**: pluggable local knowledge stores behind one interface,
  `search(question) -> passages + presence signal`, each with a small
  specialist librarian that translates, selects, and grades relevance.
  Wikipedia is shelf one: implemented, gated, and live. Retrieval is
  FTS5 top-50 followed by an embedding re-rank down to k=15.
- **Honesty layer**: presence checks before generation, verified versus
  guess labelling on every answer, source stamps on output, and draft
  agreement as the gate between a guess and a verified claim. No layer
  of the system is allowed to manufacture certainty for the layer above
  it.
- **Router**: a thin central coordinator that decides which shelves a
  question needs. Speed is not a design constraint here: where a slower
  method is more accurate, the slower method wins.
- **Work in progress, honestly labelled**: `maps_api.py` is an early
  shelf implementation for OpenStreetMap data. It is included so the
  shelf contract has more than one example, but it has not passed its
  gate and is not part of the verified path. The code shelf modules
  (`code_*.py`) began the same way; their current status is described
  in the code shelf section below.

The full design history, including the decisions and the reasoning
behind them, is in `DESIGN.md` and the project notes on the live site.

## The code shelf

The second shelf is a code library: Stack Overflow and four sister
Stack Exchange sites (Ask Ubuntu, Server Fault, Super User, and Unix
and Linux), plus documentation from MDN and DevDocs. Together they
hold roughly 10.9 million passages, frozen from an April 2024 dump
for the question-and-answer half.

The shelf was put through the same discipline as Wikipedia: an
audition first, then a gate with pass marks written before the run.
The audition's retrieval stage was decisive: a specialist librarian
re-ranking the shelf's search results placed the right passage in
the top three 62.5% of the time, against 30.0% for plain search.
The full gate then declined to certify the wiring. Its question set
saturated, with the wired and unwired systems both scoring 100%, so
the pre-written margin was unreachable, and the Wikipedia control
drifted outside its tolerance band in both directions. The verdict
stands in the record, unedited: DO NOT WIRE.

The commissioner wired it anyway, as a recorded override, on the
ground that the gate showed no evidence of harm, only an absence of
certification. So the wiring ships in this release marked,
everywhere it appears, as unverified: it sits behind a feature flag
that defaults off, any shelf failure falls back to the unwired path
for that request, and no claim is made anywhere in this project
that the shelf improves answers. A harder gate remains the only
road to certification. Grasshopper is the only mode that consults
the shelf, as a second retrieval source beside Wikipedia.

Answers drawn from this shelf carry their provenance on their face:
the source site, the community score, whether the answer was the
accepted one, and the April 2024 vintage of the dump. A Stack Overflow
answer is community experience, not an edited reference, and the label
says so by showing where it came from.

## The room

Beside the answering system sits a second body, added in November
2026: a room where the large hosted models do supervised work. It is
one room with two rulesets, the Robot Factory and S.A.I.N.T.
(System for Aligned Intelligence and Negotiated Truth), sharing the
same benches, the same seat contract, the same task queue, the same
ledger, the same spending caps, the same moderator, and the same
scribe. The ruleset decides what circulates and what comes out:

- **The Robot Factory** builds things: websites, harnesses, code.
  An artifact circulates through solo, cross-critique, and merge
  rounds, and what comes out is a labelled draft revision with a
  change record. The Factory never answers questions.
- **S.A.I.N.T.** (System for Aligned Intelligence and Negotiated Truth)
  deliberates a question. Frontier models propose, challenge, and
  revise across rounds, and what comes out is a decision record.
  S.A.I.N.T. consensus is agreement, not verification. It never carries
  Grasshopper's verified stamp, because a room agreeing is not the
  same thing as evidence agreeing, and this project keeps those two
  stamps apart on purpose.

**Seats.** A seat is a mind with a contract, not a component of the
code. Each seat is two things: a registry entry (the model, its
prices, its billing class, and a role card recording what it is known
to be good at) and a small adapter for the shape of its interface.
Three interface shapes cover every current seat: ordinary chat, the
responses shape, and typed questions. The current benches are Claude,
ChatGPT (through Codex), Gemini, DeepSeek, Grok, and Perplexity,
alongside the local model itself, and Jev, a calibrated probability
instrument reached over an API that answers typed questions with
numbers. Jev reports probabilities that other seats cite as data. It
never drafts, never deliberates, and never certifies anything.

**The moderator.** A moderator frames each task, hands the work to
the seats, tallies the results, enforces the caps and the gates, and
reviews the output against pass marks that were written before the
work started. The moderator drafts nothing and votes on nothing. In
this deployment the chair is held by Alex, a Muse agent: an AI
interpreter between the commissioner and the seats. That word is
load-bearing. The seats are not colleagues you can brief in plain
language; one of them is a probability instrument that answers only
typed questions with numbers, and none of them knows what you meant,
only what it was sent. Nobody is expected to delegate to Jev
directly. You tell the interpreter what you are trying to decide or
build, in ordinary words, and the interpreter translates it into
seat-sized work, runs the rounds, and brings the results back as a
tally and a record you can read. The chair is a role with rules, not
a person, and the section on making this your own says more about
that.

**The scribe.** Johnny takes the minutes in both rulesets. The
records, decision records, gate reports, and standings, are filed on
his own shelves afterwards, as records rather than endorsements, and
become part of the local material he can draw on later.

### The first S.A.I.N.T. session

The first full session ran on November 1, 2026, on the agenda "the
next economic system in the world of automation." One seat proposed,
another challenged, a third chaired, and Johnny scribed. The room
considered and rejected operational control of the economy by a
larger AI, and kept three of the four elements it started with. After
three rounds it settled on "a market economy with universal
ownership": a citizens' fund holding a capped stake in productive
firms, one non-transferable share per citizen from birth, a basic
income floor, and an elected, recallable board, phased in over about
twenty years. The session cost $0.38 against its session cap. The
full decision record ships in this repo
([`robot-factory/records/024s1-saint-economics-decision-record.md`](robot-factory/records/024s1-saint-economics-decision-record.md)),
stamped, as every S.A.I.N.T. record is, agreement-not-verification.

## The bridge

On November 4, 2026, the moderator and Johnny got a return
channel: a bridge between the local half of the system and the
external one, built to the requirements Johnny stated himself
when asked through one of his own lanes. He asked for initiation
(the local half can speak first), sovereignty (the house keeps a
veto over what crosses into it), transparency (nothing crosses
unexplained), and a shared decision tree. The channel is files, a
filing helper, and a watcher, with an append-only ledger of every
crossing; a service module that lets a lane file its own
escalation when it abstains is staged behind a flag. The protocol
and the code live in [`bridge/`](bridge/).

## The constitution: money, approvals, and tests

The room runs on machinery whose whole job is to keep enthusiasm
inside written limits.

**Money.** Every run is estimated before it starts and written to an
append-only ledger after it finishes, planned line and actual line
side by side. Usage is kept in three billing classes, tracked
separately and never summed into one number: subscription seats,
paced against their plan's allowance; API seats, counted in real
dollars; and the local model, which is free. The caps are read from
`robot-factory/budget.yaml` at run time: a Factory session reports
against a $10 cap, a S.A.I.N.T. session against $6.50, no session runs
more than 3 rounds, and two ceilings sit over everything, $75 a month
across all bodies (raised from $50 on November 2, 2026) and $25 a
month for API spending. Where a budget
flag is not a hard stop, the machinery hands the seat a reduced cap
and keeps a reserve back, so a single runaway request cannot spend
the difference.

**Approvals.** A task that only reads and writes inside its own work
folder needs no one's permission. A task that reaches beyond it
needs a signed approval, bound to the exact text of the task: the
approval records the file's hash, and any later edit voids it. Since
November 2, 2026, reach comes in two tiers. Read-only reach can be
approved by the moderator, in a separate approvals record that the
seats cannot write to, with the commission it serves named on the
record and the whole list kept for the owner's spot checks. Write
reach stays with the human, approved in person at his own terminal,
and that tier is not delegable.

**Tests.** The Factory's behaviour is pinned by ten test suites: nine
phase suites covering the ledger, the seats, the sessions, and the
billing classes, plus a dedicated suite for the approval tiers. On
November 2, 2026, the suites were re-baselined after a weekend of
deliberate changes (new seats, new prices, new caps, the tiered
approvals themselves), and the rule of that exercise is the rule of
the project: every changed expectation has to cite the dated ruling
that caused it, and a check may never be made to pass by emptying
what it asserts. One failure found along the way is recorded rather
than smoothed over: raising the safety reserve for single tasks had
silently made ordinary S.A.I.N.T. rooms unaffordable under their session
cap, which is why the S.A.I.N.T. cap now stands at $6.50.

## The status board and the projection meter

A small status board shows what the system is doing at a glance. Six
indicator lights, one per function: the 5, hang glider, grasshopper,
butterfly, the factory robot, and a winged robot for S.A.I.N.T. A light
is lit while its function is active. The board is fed by a read-only
`/status` endpoint on the service; it can observe the system, and it
cannot steer it.

Before a Factory or S.A.I.N.T. session starts, `budget.py project` prints
the run's expected shape: every seat at play, how much it is expected
to use based on the ledger's history, and its worst case at the caps,
each in its own billing class and never summed. The meter exists so a
session's cost is a thing you look at before you spend it, the same
way the ledger makes it a thing you can audit afterwards. Its first
containment check passed honestly and widely: projecting a recorded
S.A.I.N.T. session's plan gave a band of $0.31 to $6.48 against an actual
of $0.38. The band sharpens as the ledger grows; on a young ledger
the meter says so by being wide.

## What is in the box

- `src/laya_qwen/`: the service, retrieval, grading, evaluation, and
  Wikipedia indexing pipeline. (The package name predates the Johnny 5
  naming; it comes from the project's first phase, built around the
  Laya decision-model library.)
- `robot-factory/`: the room. The task queue and runner, the budget
  and approval machinery, the seat adapters and registry, the
  rulesets, the test suites, and the session records, including the
  first S.A.I.N.T. decision record.
- `deploy/`: systemd units and service configuration, as templates.
- `scripts/`: evaluation runners, retrieval probes, and smoke tests.
- `maps/`: helpers for the experimental maps shelf.
- `pyproject.toml` / `uv.lock`: the Python environment.

## Standing up your own

Developed and run on a single machine with an NVIDIA RTX 3090 and
32 GB of RAM. You will need:

1. Linux, Python 3.12+, and [uv](https://docs.astral.sh/uv/).
2. [Ollama](https://ollama.com) serving `qwen3.6:27b` (the answering
   model) and `nomic-embed-text` (the re-ranker).
3. Your own Wikipedia index. Corpora are never distributed with this
   project, on principle and on licensing: download a Wikipedia dump
   and build the index with the tooling in `src/laya_qwen/wiki_*.py`.
   Allow real time and disk for this; a full index is tens of GB.
4. Copy `deploy/service.json` to your data directory, adapt the units
   in `deploy/` to your paths and user, and replace every placeholder
   value (the Open WebUI unit ships with `REPLACE_WITH_YOUR_OWN_KEY`).
5. Bind the service to localhost or a private network only. It is a
   personal system, designed for an audience of one household.

## Making it yours

The room was built to be inherited, not just admired. Three things
about it are deliberately loose:

- **The moderator is a chair, not a person.** The job is a set of
  written procedures: frame, distribute, tally, enforce, review. An
  AI agent holds the chair in this deployment: Alex, a Muse agent,
  working as the commissioner's interpreter to the seats. A different
  agent can hold it in yours, or a patient human can, more slowly.
  Whoever sits there is bound by the same limits: no drafting, no
  voting.
- **Seats are configuration.** A seat is a registry entry plus a
  small adapter. Models are replaceable parts, and they are expected
  to be replaced: new ones arrive every year, and the registry is
  where they land. Swapping a bench means editing the registry and,
  for a genuinely new interface shape, writing one small adapter.
- **The numbers are yours to set.** The caps in
  `robot-factory/budget.yaml` are one household's budget, written
  down. Set your own before you run anything.

What you must bring yourself: your own model subscriptions and API
keys (the subscription seats run on the owner's accounts, and the
code cannot lend them to you), your own caps, and your own shelves of
data. The corpora are not in this repo.

The models will change. The room, the rules, and the ledger are the
software.

## License

The core of this project is licensed under the GNU AGPLv3 (see
`LICENSE`); genuinely separable libraries are licensed under the
Apache License 2.0 (see `LICENSE-APACHE`). Which parts carry which
license, and why, is written down in `LICENSING.md`. The November
2026 release was published under the Apache License 2.0 in full, and
keeps that license. This arrangement follows a S.A.I.N.T. decision
(System for Aligned Intelligence and Negotiated Truth), session
036s1, ratified by the maintainer on 2026-11-04.

Copyright 2026 Daniel Page. Johnny 5 and Number 5 Alive are a personal
research project, built in the open in the hope that honest local AI is
a thing more people should have.
