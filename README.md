# Johnny 5: Number 5 Alive

A local-first AI harness for a personal computer. It runs a capable open
model on hardware you own, checks its answers against a local library
before it speaks, and labels everything it says: verified, or guess.

Most AI systems optimize for fluency. This one optimizes for knowing
when it does not know. Abstaining is a first-class outcome here, not a
failure mode.

Live project page: https://number5alive.com

## The modes

The answering system has three modes, each special for a different
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

The service exposes an OpenAI-compatible chat endpoint, so any client
that speaks that protocol (Open WebUI is included as an optional front
end) can sit in front of it.

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
- **Work in progress, honestly labelled**: `maps_api.py` and the
  `code_*.py` modules are early shelf implementations for OpenStreetMap
  data and a code reference corpus. They are included so the shelf
  contract has more than one example, but they have not passed their
  gates and are not part of the verified path.

The full design history, including the decisions and the reasoning
behind them, is in `DESIGN.md` and the project notes on the live site.

## What is in the box

- `src/laya_qwen/`: the service, retrieval, grading, evaluation, and
  Wikipedia indexing pipeline. (The package name predates the Johnny 5
  naming; it comes from the project's first phase, built around the
  Laya decision-model library.)
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

## License

Apache License 2.0. See `LICENSE`.

Copyright 2026 Daniel Page. Johnny 5 and Number 5 Alive are a personal
research project, built in the open in the hope that honest local AI is
a thing more people should have.
