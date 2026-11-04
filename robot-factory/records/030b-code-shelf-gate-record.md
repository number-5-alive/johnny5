# Record: 030b-code-shelf-gate

*Gate run 2026-11-02 on argo; verdict scored by the seat's own
analyze.py from the completed audition output (audition script
run_all.py finished 22:33 CT after the seat session ended at its
2-hour wait limit; a watcher ran the scorer and delivered the
verdict). Scorer output: work/030b-code-shelf-gate/analysis.json.
Full build record: work/030b-code-shelf-gate/REPORT.md.*

## Verdict: DO NOT WIRE

The gate declined to certify the code shelf for wiring into the
answering lanes. The verdict stands unedited; the commissioner's
override that followed it is a separate record
(031b-commissioner-override-2026-11-03.md), and the wiring built
under that override is marked unverified everywhere it appears.

## Pass marks, as pre-written, and the scored results

- **G1 (wired beats bare by +10 on the audition set): FAIL.**
  Wired 100.0% vs bare 100.0%. The set saturated: at a 100%
  ceiling the pre-written margin was unreachable. The result
  shows no harm and no measurable gain on these questions.
- **G2 (agreed accuracy at or above the 80% bar): PASS.**
  Agreed accuracy 100.0% (39 agreed).
- **G3 (Wikipedia control inside +/-3 of the Oct 30 gate
  aggregates): FAIL.** Table 80.0% (delta -3.8 against 83.8%);
  prose 100.0% (delta +22.0 against 78.0%). The control moved
  outside tolerance in both directions, so the run cannot
  certify the comparison it was built to make.

## Stage 1 (retrieval, scored separately)

The librarian re-rank WON its stage: gold-in-top-3 62.5% for the
librarian against 30.0% for plain top-3 retrieval (n=40; API
questions 65% vs 25%; debugging questions 60% vs 35%). The
librarian's API top-3 carried 23 documentation passages against
plain retrieval's 11, and its debugging top-3 was entirely Q&A,
which is the measured basis for the wiring's precedence rule:
documentation first for API-fact questions, Q&A first for
debugging questions.

## Reading of the result

The gate did what gates in this project do: it declined to
certify, it did not show the shelf harms or fails to help. The
wiring question on easy questions is unproven; on hard
questions it is untested. A harder gate remains the only road
to certification. The wiring that exists was built under the
commissioner's override (task 031b) with safeguards: feature
flag default off, fallback to unwired behaviour on any shelf
failure, service-log marking code_shelf="unverified",
provenance on every shelf-informed answer, and no public claim
that the shelf improves answers.
