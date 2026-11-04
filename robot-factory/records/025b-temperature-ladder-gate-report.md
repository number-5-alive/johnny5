# 025b Gate Report: temperature ladder (F vs L) and the bare "no malfunction" lane (B)

Generated 2026-11-02 01:02 -0600 by `make_report.py` from `raw/results-*.jsonl`.

**Status: COMPLETE.** All three arms finished on n=100 (50 table + 50 prose).

## Sample size: cut to n=100

The pilot (6 questions: table ids 16, 21, 73; prose ids 26, 35, 49) took 2564 s across all three arms, about 427 s per question. The full n=120 run projected to **14.2 h, over the 8 h limit**, so per the brief the run is **cut to n=100** (the first 50 table ids and the first 50 prose ids by sorted id, the same selection rule). Even n=100 projects to about 11.9 h. The cut is the brief's prescribed remedy; it does not bring the run under 8 h. The pilot rows are reused in the full run: same code, same parameters, and the ids are in the n=100 set. Details are in `logs/projection.txt`.

## Pass marks (fixed before any run, restated)

- **V1**: L accuracy among agreed answers ≥ F accuracy among agreed answers.
- **V2**: L agreement rate ≥ F agreement rate − 10 points.
- **B1**: B accuracy-when-stamped ≥ single-draft (T=0.2) accuracy + 15 points.
- **B2**: B accuracy-when-stamped ≥ 60%.
- **B3**: B stamp rate ≥ 20%.
- A failed mark is a result. No re-runs with adjusted prompts, ladders or thresholds were made.

## Arms F and L (live verified lane vs. temperature ladder), n=100

| arm | split | n | agreed | agreement rate | accuracy among agreed | overall accuracy | decisions |
|---|---|---|---|---|---|---|---|
| F | all | 100 | 80 | 80.0% | 95.0% (76/80) | 76.0% (76/100) | agreed_answer 80, agreed_decline 12, unverified_guess 8 |
| F | table | 50 | 41 | 82.0% | 95.1% (39/41) | 78.0% (39/50) | agreed_answer 41, agreed_decline 5, unverified_guess 4 |
| F | prose | 50 | 39 | 78.0% | 94.9% (37/39) | 74.0% (37/50) | agreed_answer 39, agreed_decline 7, unverified_guess 4 |
| L | all | 100 | 81 | 81.0% | 93.8% (76/81) | 76.0% (76/100) | agreed_answer 81, agreed_decline 14, unverified_guess 5 |
| L | table | 50 | 41 | 82.0% | 95.1% (39/41) | 78.0% (39/50) | agreed_answer 41, agreed_decline 6, unverified_guess 3 |
| L | prose | 50 | 40 | 80.0% | 92.5% (37/40) | 74.0% (37/50) | agreed_answer 40, agreed_decline 8, unverified_guess 2 |

Single-draft accuracy by draft temperature (each draft graded on its own; diagnostic only, not a mark):

- F: {'1.0': 76.4}
- L: {'0.2': 76.0, '0.4': 77.0, '0.6': 77.0, '0.8': 77.0, '1.0': 75.0}

**V1: FAIL.** L 93.8% vs F 95.0%.  
**V2: PASS.** L 81.0% vs F 80.0% − 10 = 70.0%.

## Arm B (bare model, no retrieval, ladder 0.2/0.5/0.8/1.1/1.4), n=100

| split | n | stamped | stamp rate | accuracy when stamped | single draft T=0.2 accuracy (all n) | T=0.2 accuracy on the stamped subset | winner accuracy (all n) |
|---|---|---|---|---|---|---|---|
| all | 100 | 16 | 16.0% | 31.2% (5/16) | 15.0% | 31.2% | 12.0% |
| table | 50 | 5 | 10.0% | 20.0% (1/5) | 8.0% | 20.0% | 6.0% |
| prose | 50 | 11 | 22.0% | 36.4% (4/11) | 22.0% | 36.4% | 18.0% |

Judge errors (unparseable judge output, which gives no stamp): 0. Draft accuracy by temperature: {'0.2': 15.0, '0.5': 10.0, '0.8': 9.0, '1.1': 6.0, '1.4': 11.0}

**B1: PASS.** 31.2% vs 15.0% + 15.  
**B2: FAIL.** 31.2% vs 60%.  
**B3: FAIL.** 16.0% vs 20%.

## Recommendation

- **Ladder (L) for the live verified lane:** does not pass both marks (V1 and V2). **Keep the live lane at T=1.0.**
- **Bare "no malfunction" lane (B):** fails B2, B3. **Do not ship it.** The stamp would certify agreement of the model with itself, not correctness. `nomalfunction.py` stays a prototype.

## Fidelity of arm F to the live lane (taken from the read-only `~/laya-qwen` source, nothing retyped)

- Model `ollama.MODEL` = `qwen3.6:27b`. The unit sets no `LAYA_QWEN_MODEL`. Ollama at 127.0.0.1:11434.
- Draft options `ollama.THINKING_OPTIONS` (temperature 1.0, top_p 0.95, top_k 20), num_ctx 16384, num_predict `pipelines.DRAFT_TOKENS` = 3000, think=True. Arm L and arm B change **only** the temperature.
- Retrieval: `pipelines.default_retriever(pipelines.adopted_config())`, k = `service.K` = 15, over `~/laya-data/wiki-20261001.db`, which `retrieval.py` opens with a `?mode=ro` URI.
- Prompt `pipelines.rag_messages`. Agreement check `pipelines.cluster` + `pipelines.decide` called as-is (AGREE=4 of N_DRAFTS=5). "Agreed" means decision == `agreed_answer` (the live Verified outcome).
- Scoring: `grader.grade` (the SimpleQA rubric used by `score_run.py` → `eval.run_one`), applied to the text the lane would present and to each draft.

## Interpretations and decisions (stated, fixed before the full run)

1. **"Temperature 0.0 appears nowhere"** was applied to *drafting*. `common.draft_options` refuses T=0.0. The live F/L agreement check (`pipelines.cluster`, `GRADER_OPTIONS` T=0.0) and the grader (T=0.0) were kept as they are, because the brief also requires the *same* agreement check and the same scoring discipline. Changing them would make F not the live lane. If the stricter reading was intended, F/L agreement and all grades would need re-scoring.
2. **No draft deadline**: all 5 drafts always run. The live lane stops at `DRAFT_DEADLINE`=480 s and decides with what it has; that deadline depends on wall-clock time and GPU contention, so it was left out to keep the arms comparable.
3. F and L share **one retrieval per question** (the retriever is deterministic).
4. Arm B drafts use think=True with the live options except temperature. The B judge is the same model, thinking off, T=0.2, with a JSON schema. Declines and empty drafts are put in no cluster and cannot earn the stamp. Drafts the judge leaves out become singleton clusters. If the judge output cannot be parsed, there is no stamp.
5. **B1 baseline** = the T=0.2 draft's accuracy over all n (the same question set as the stamp rate). Its accuracy on the stamped subset alone is also reported.
6. The pilot rows were reused (same code and parameters).
7. **Shared GPU**: one RTX 3090 also serves the live service. Ollama runs one request at a time, so while the harness ran, live requests queued behind it (higher latency). Live behavior was not changed.
8. The CLI test ("What is the capital of Australia?" → Canberra, 5/5, stamped) is in `nomalfunction-record.jsonl`. It is a smoke test, not part of any mark.

## Reproduce

```bash
cd ~/robot-factory/work/025-ladder-gate
export PYTHONDONTWRITEBYTECODE=1
PY=~/laya-qwen/.venv/bin/python
$PY run_gate.py --arms FL --per-stratum 50   # arms F and L (resumes from raw/ if present)
$PY run_gate.py --arms B  --per-stratum 50   # arm B
python3 analyze.py                            # -> gate-numbers.json
python3 make_report.py                        # -> GATE-REPORT.md
./nomalfunction.py "your question"            # the prototype CLI (or pipe the question on stdin)
```
To reproduce from scratch, move `raw/` aside first; otherwise the harness resumes. The pilot is the same commands with `--per-stratum 3`.

## Files

- `common.py`: live parameters (imported), ladders, draft call, arm B judge and stamp rule
- `run_gate.py`: resumable harness. `analyze.py`: numbers and verdicts. `make_report.py`: this report
- `nomalfunction.py`: prototype CLI, which prints the winner and the stamp line and appends the spread to `nomalfunction-record.jsonl`
- `raw/drafts-{F,L,B}.jsonl`: every draft, checkpointed as it arrived (content, thinking, tokens, seconds). `raw/results-{F,L,B}.jsonl`: per-question rows
- `gate-numbers.json`, `logs/` (pilot and full-run logs, `projection.txt`)
