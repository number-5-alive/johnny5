# laya-qwen: design

Goal: fewer factual errors on general-knowledge questions, fully local. Single user via Open WebUI; multi-minute answers are acceptable.

Principle: add one component at a time and keep it only if it measurably helps against the previous stage.

## Infrastructure (argo, via Tailscale)

- Hardware: RTX 3090 24 GB, 30 GB RAM, NVMe `/` (536 GB free), `/mnt/hub` 8.5 TB (likely HDD).
- Ollama on `:11434` (used directly; `:11435` is the user's own `~/ollama-proxy.py`).
  - `qwen3.6:27b` (Q4_K_M, ~17.8 GB), `nomic-embed-text`.
  - `override.conf`: `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_HOST=0.0.0.0:11434`.
  - `laya-qwen.conf` (added 2026-10-14): `OLLAMA_NUM_PARALLEL=5`, `OLLAMA_MAX_LOADED_MODELS=2`.
  - **Ollama 0.33.2 ignores NUM_PARALLEL for qwen3.6** ("model architecture does not currently support parallel requests", architecture=qwen35; llama-server is started with `-np 1`). 5 concurrent requests are processed one after another (51 tok/s single vs 46 tok/s aggregate for 5).
  - qwen3.6 (16k context) + nomic fit together fully on the GPU: ~19 GB of 24 GB.
  - qwen3.6 has priority; avoid qwen3-coder workloads during evals.
- Orchestrator: Python 3.11 + uv + FastAPI, systemd on argo, port 8100, OpenAI-compatible, no auth (tailnet only). Streams progress status.
- Laya (if adopted, stage 4): `laya-multilingual` (1,024-token limit), imported in-process, CPU.
- Open WebUI: Docker on argo, pointed at the orchestrator.
- Code: `~/projects/laya-qwen` on Mac, rsynced to `~/laya-qwen` on argo (uv, Python 3.12). Evals from stage 2 on run on argo. During development, Laya runs on the Mac.

## Stages

Each stage is evaluated on the same 200 held-out SimpleQA questions and compared with the previous stage.

1. **Baseline:** qwen3.6 alone, thinking on.
2. **Retrieval:** English Wikipedia (`wikimedia/wikipedia` 20231101.en, pre-cleaned plain text), ~250-word chunks, SQLite FTS5 keyword index (porter stemming, title weighted 5x), top 50 re-ranked with nomic-embed-text, top 5 given to qwen.
   - Parquet shards on `/mnt/hub/data/wikipedia/20231101.en` (HDD); index at `~/laya-data/wiki.db` on NVMe (37.9 GB after optimize).
3. **Agreement check:** 5 parallel drafts (thinking capped at ~2k tokens, temperature 1.0). If the drafts disagree on the core answer, return a best guess clearly labelled **unverified**. If this is over the time limit, fall back to 3 drafts with a 3-of-3 rule.
4. **Laya as a cheap checker** (decisions of 2026-10-15 below supersede the original sketch in this item): calibrate on ~2k FEVER examples (fine-tune only if dev accuracy is below ~80%). Run it head-to-head against qwen-as-judge (thinking off) on the same support/agreement checks. Keep Laya only if its accuracy is comparable and it is clearly faster.
   - Router: Laya noul "does this question depend on specific facts?"; below 0.3, skip retrieval.
   - Passage checks: choice {supports, contradicts, unrelated}.
5. **Claim-level verification (optional):** split long answers into atomic claims, check each one, drop claims that are contradicted, or disputed with no source found, then rewrite from the kept claims only and remove any rewritten sentence the checker doesn't support. Build only together with a long-form eval (FActScore-style); SimpleQA can't measure it.
6. **Service and Open WebUI.**
7. **Freshness (planned; not built until stages 1–6 are measured):**
   - **Snapshot swaps:** periodically build a full index from a newer Wikipedia dump next to the current one, swap it in, and keep the old index for rollback.
   - **Daily delta updater:** apply changed articles to the FTS index (delete the article's old rows, insert the new text). Checkpointed so it can resume.
   - **Knowledge currency:** store the corpus as-of date and a per-article revision date. Stamp answers with how current their sources are; questions about events after the corpus date abstain or escalate.
   - **Live web retrieval (optional):** a fallback source for when the corpus is too old.

### Constraints on current work (to keep stage 7 possible)

- Retrieval sits behind an interface so the source is pluggable (local index, delta-updated index, live web).
- The index keeps a stable per-article key (Wikipedia page id) and a revision date.
- The corpus is frozen during the benchmark stages: every stage comparison runs against the November 2023 snapshot.

Time limit: 10 minutes per question. When it is hit, return what has been verified, or a labelled unverified best guess.

## Results (200 held-out SimpleQA questions)

| Stage | Correct | Incorrect | Not attempted | Correct given attempted | F-score | Median s/question |
|---|---|---|---|---|---|---|
| 1 Baseline | 16.5% | 79.0% | 4.5% | 17.3% | 16.9 | 32 |
| 2 Retrieval | 60.0% | 18.5% | 21.5% | 76.4% | 67.2 | 26 |
| 3 Agreement (5 drafts, 4-of-5) | 62.5% | 16.5% | 21.0% | 79.1% | 69.8 | 99 |
| 2.1 Retrieval: title match + normalization, k = 15 | 66.0% | 14.0% | 20.0% | 82.5% | 73.3 | 26 |
| 3 at k = 15 (re-baseline, `agree21_k15`) | 63.5% | 10.0% | 26.5% | 86.4% | 73.2 | 89 |

Stage 2.1 (final, single held-out run, 2026-10-15): vs stage 2, question by question, 7 incorrect→correct, 6 not attempted→correct, 9 incorrect→not attempted, 6 not attempted→incorrect, 1 correct→incorrect. Adopted as the shipping retrieval (`rag21_k15`). Stage 3 is re-baselined at k = 15 (`agree21_k15`); the stage 3 row above was measured at k = 5.

Stage 3 re-baseline at k = 15 (2026-10-16): **verified** 178 (134 agreed answers + 44 agreed declines): 127 correct / 6 incorrect, **95.5%** correct given attempted; **unverified guesses** 22: 0 correct / 14 incorrect / 8 not attempted. If unverified guesses abstained: 63.5% correct, **3.0% incorrect**. vs stage 2.1 (`rag21_k15`): 12 incorrect→not attempted, 3 correct→not attempted, 2 correct→incorrect, 2 not attempted→incorrect; F is unchanged (73.2 vs 73.3), the trade is fewer wrong answers for more declines at ~3.4x the time. qwen grouping: 375 s total, 1.88 s/question (argo GPU). 51 of 1,000 drafts hit the token cap; no errors.

Stage 3 split by label: **verified** (171: 133 agreed answers + 38 agreed declines) 121 correct / 11 incorrect, 91.7% correct given attempted; **unverified guesses** (29) 4 correct / 22 incorrect, 15.4%. The label separates reliable from unreliable answers. If unverified guesses abstained instead: 60.5% correct, 5.5% incorrect, 34.0% not attempted.

Stage 3 vs 2, question by question: 120 correct in both; 3 incorrect→correct, 2 not attempted→correct, 7 incorrect→not attempted, 6 not attempted→incorrect (mostly unverified guesses where stage 2 had declined). Headline changes of 2–3 points are within sampling noise at n=200; the verified/unverified split is the real result. 46 of 1,000 drafts hit the 3,000-token cap; no clustering errors, no deadline cuts; full run 6.7 hours.

Stage 2 vs 1, question by question: 91 incorrect→correct, 35 incorrect→not attempted, 9 regressions (7 correct→not attempted, 2 correct→incorrect).

### Stage 2 regressions (9 questions correct at baseline, not correct with retrieval)

| Id | Question (short) | Outcome | Category | What happened |
|---|---|---|---|---|
| 609 | '04 ALCS Game 2, 8th-inning leadoff single | not attempted | Retrieval miss (keyword stage) | Answer passage exists (2004 ALCS article) but wasn't in the top 50: query says "'04", "8th", "ALCS"; text says "2004", "eighth", "American League Championship Series". |
| 4215 | Rastriya Prajatantra Party founding date | not attempted | Retrieval miss (keyword stage) | Article says "formed ... on 29 May 1990" in its History section; that passage wasn't in the top 50 (question says "founded"); top 5 had the lead passage ("in 1990"). |
| 2229 | NVS-01 launch date | not attempted | Retrieval miss (re-rank stage) | NVS-01 article was in the top 50 and states 29 May 2023; re-ranking filled all 5 slots with generic Satish Dhawan Space Centre passages. |
| 4031 | First author of the 2021 ADHD consensus statement | incorrect | Retrieval miss (partial) | Top 1 was Stephen Faraone's article, but not the passage saying he "led the International Consensus Statement"; qwen then produced a name ("Steven W. Tsai") found in no passage. |
| 4212 | First computerized diver's watch | not attempted | Retrieval miss (likely corpus gap) | All 5 slots went to the "Diving watch" article; no passage in the top 50 credits Seiko with a computerized diver's watch. |
| 1930 | President with a posthumous Raven Award, 1959 | not attempted | Retrieval miss (corpus gap) | The "Raven Award" article is one passage with no recipient list (lists and tables are stripped from this dataset). |
| 3611 | Number of A-frames in the 1961 Stebel House | not attempted | Retrieval miss (corpus gap) | No Stebel House article; the Harry Gesner article doesn't mention it. |
| 1751 | Favourite food of the tent caterpillar per the 1898 NY report | not attempted | Declined despite good passages | Top 5 included "often feed on the ... black cherry tree (Prunus serotina)"; qwen declined because no passage cited the 1898 report. |
| 342 | Age gap between G. F. Watts and Ellen Terry | incorrect | Anchored on a passage (misleading, not wrong) | Passage: married "seven days before her 17th birthday, when Watts was 46" → qwen said 29 years; birth years 1817/1847 give the gold 30. The gold is arguably borderline (birthdays 4 days apart). |

Totals: 7 retrieval misses (3 fixable by retrieval, 1 partial, 3 likely corpus gaps), 1 declined, 1 anchored.

### Possible stage 2.1: retrieval fixes (measured on their own, not folded into stage 3)

Each targets the fixable misses above; all use the frozen snapshot.

1. **Per-article cap in the top 5** (e.g. at most 2 passages per article), so one broadly relevant article can't crowd out a specific one (2229, 4212).
2. **Article expansion:** when an article title strongly matches the question (e.g. "NVS-01", "Rastriya Prajatantra Party", "Stephen Faraone"), add all of that article's passages to the re-rank pool via `passage_article` (4215, 4031, 2229).
3. **Query normalization:** expand two-digit years ("'04" → 2004), ordinals ("8th" ↔ "eighth") and known abbreviations ("ALCS"), and add simple synonyms ("founded" ↔ "formed", "established") (609, 4215).

How to measure: first a cheap retrieval-only check (is the gold answer in the top 5?) on the dev split, never the held-out 200, then a single held-out `rag` run with the change, compared with stage 2. The 9 regressions are a diagnostic, not a tuning set. Corpus gaps (stripped lists, infoboxes, missing articles) are out of scope for 2.1 and belong to stage 7.

### Stage 2.1 tuning results (500 dev questions, gold answer in top 5)

| Config | Recall@5 | Gained | Lost |
|---|---|---|---|
| stage 2 | 51.2% | – | – |
| cap 2 per article | 49.0% | 2 | 13 |
| title match | 51.6% | 2 | 0 |
| top-2 article expansion | 51.0% | 3 | 4 |
| query normalization | 51.4% | 1 | 0 |

Decisions: drop the per-article cap and top-article expansion. Keep title match and query normalization permanently (no losses), but they don't count as the stage 2.1 improvement.

Keyword-stage recall (gold in the first N keyword candidates): top 5 49.8%, top 50 61.8%, top 200 66.2%. Re-ranking loses ~10.6 points between the top-50 pool (61.8%) and the final top 5 (51.2%).

**Adoption rule for k (passages given to qwen), fixed before the k results were seen (2026-10-15):** with the current 50-candidate pool, adopt the smallest k in {5, 10, 15, 20} whose post-re-rank recall is at least 56.5% on the same 500 dev questions, i.e. it recovers at least half of the 10.6-point loss. If none qualifies, k stays 5. Applied mechanically.

Then, at the winning k: run the full `rag` pipeline end to end on dev questions and compare answer correctness against k=5 (presence is a ceiling, not the deciding metric). Then one held-out run with the adopted configuration. The winning k also re-baselines stage 3, whose split was measured at k=5.

**k results (pool 50, same 500 dev questions):** recall@5 51.2%, @10 54.2%, **@15 57.0%**, @20 58.4%. The rule selects **k = 15** (recovers 5.8 of 10.6 points). A pool-100 pass was invalid (the script changed `CANDIDATES` after import; the default argument had already bound 50) and isn't used.

**End-to-end check at k = 15 (in progress):** `rag21_k5` vs `rag21_k15` on 200 dev questions (seed 2101), both with title match + normalization. Rule (replaces the earlier proposal; set by the user 2026-10-15 after an interim look at 178/200, before the final 22 dev answers were seen): a candidate k ships if, on the full 200-question dev set, its F-score (harmonic mean of overall correct rate and precision among answered) exceeds the control's (k = 5) AND its correct count is not lower. Incorrect-to-abstain conversions count in the candidate's favor only through F. The winner then faces one held-out run; the held-out result is final. Rule changes are made before results are complete, never after.

**End-to-end result (200 dev questions, full set):**

| | Correct | Incorrect | Not attempted | Correct given attempted | F-score | Median s/question |
|---|---|---|---|---|---|---|
| k = 5 (control) | 116 | 43 | 41 | 73.0% | 64.6 | 26 |
| k = 15 | 117 | 34 | 49 | 77.5% | 66.7 | 27 |

k = 15 passes (F 66.7 > 64.6; correct 117 ≥ 116) and goes to one held-out run (`rag21_k15`); that result is final.

### Audit of 20 dev questions missing from the keyword top 200

| Bucket | Count | Examples |
|---|---|---|
| Present, gold worded differently | 1 | Marsan: "apprenticeship as a printer" vs "apprentice printer" |
| Present (verbatim), not retrieved | 2 | V. V. Giri: "fourth president" vs "4th" (now covered by normalization); Thirunavukkarasar: fact in his own article, question points elsewhere |
| On the Wikipedia page, stripped from this dataset (tables/lists) | 3 | Award recipient lists ("Recipients have been:" followed by nothing); RTO code table (probable) |
| Not in this corpus's text | 14 | Song lengths, cricket umpires, game patch dates, soundtrack release dates; 3 partial (year without date, age instead of date, 2017 figure instead of 2019) |

The answer matcher undercounts little (1/20), so the ~66% keyword ceiling is real for this corpus. Most misses are corpus coverage (17/20), which is stage 7 territory: an HTML-based dump that keeps tables for the stripped cases, and fresher or live sources for the rest.

### Between stages 2 and 3: retrieval interface and article tables

- `Retriever` interface; each `Passage` carries `source`, re-rank `score`, `passage_id`, `page_id`, `rev_date`.
- Side tables `articles` (6,407,814 rows) and `passage_article` (17,624,272 rows) added beside the untouched `passages` table.
- Verification: every passage mapped, no orphans, no title/url mismatches; 20 random articles re-chunked from source matched their mapped passages exactly; top-5 retrieval for all 200 questions identical before and after (titles, text hashes, scores).

### Stage 4 decisions (written 2026-10-15, before any Laya result exists)

- **Q1, scope:** Laya competes on draft grouping only ("do these two answers say the same thing?"), replayed on the drafts of the k = 15 stage 3 re-baseline (the shipping pipeline's set), which are graded. No new GPU time for the replay. Passage-support checks are out of scope until a stage 5 exists.
- **Q2, rule:** Laya wins only if BOTH hold:
  - (a) the verified answers' correct-when-answering rate is no more than 1 point below qwen's grouping on the same drafts, and
  - (b) the grouping step's wall-clock time over the same 200-question draft set is at least 5x faster, each checker measured on the hardware it would run on in the final system (Laya: argo CPU, in-process; qwen: argo GPU via Ollama).
- **Q3, Laya cutoff tuning (written 2026-10-15, before any Laya result exists):** option (b). Laya's two cutoffs ("same final answer?" per draft pair; "declines?" per draft) are tuned on stage 3 drafts generated for ~60 tuning-split questions, labelled from the answer key, not from qwen: both-correct pairs are "same", correct+wrong pairs are "different", drafts graded not-attempted count as declines. Both-wrong pairs are excluded (their agreement can't be derived from grades).
  - Known limitation: the tuned cutoffs never see a both-wrong pair. The guard is Q2's end metric (verified answers' correctness rate), where bad grouping would surface.
  - Cutoffs are fixed at the values maximising pairwise accuracy on the tuning pairs; if a range ties for best, use its midpoint. Cutoffs are frozen before the replay runs.
  - No fine-tuning in stage 4. It may only be proposed as a separate project if Laya loses narrowly, with its own decisions written in advance.
  - **Tuning split** = questions outside the held-out 200 and outside both earlier dev samples (the 500 retrieval-tuning questions, seed 21, and the 200 end-to-end questions, seed 2101). The 60 are drawn from it with seed 4060.
- **Q4, wordings frozen (written 2026-10-15, before cutoff tuning):** the two grouping wordings are frozen as committed in `6f23ea6`: a yes/no question "Does the response decline to answer, or say the answer is unknown or not available?" per draft, and a same/different choice "Compare the final answers of response A and response B to the question" per pair. They were selected on 16 hand-written examples, with no eval or tuning data. From here, tuning sets only the two cutoffs, per Q3. If Laya loses under Q2, any future rewording is a new version of the checker and needs its own decisions written in advance; it is not a continuation of stage 4.
- **Q5, tie-breaking (written 2026-10-15, before tuning):** if the best accuracy is tied across separate cutoff ranges, use the midpoint of the widest tied range; if several ranges tie for widest, the midpoint of the highest of them. The chosen cutoff must itself achieve the best accuracy (a span midpoint outside every tied range is not permitted).
- Report the verified-answer counts for both groupings alongside the rates, so volume drift is visible even though the rule prices the rate.
- Otherwise Laya is dropped and the system stays qwen + Wikipedia + agreement. Thresholds change before results, never after.

### Stage 4 result (2026-10-16): Laya dropped

Cutoffs tuned on 60 tuning-split questions (300 drafts) and frozen in `results/stage4_cutoffs.json` (commit `bad181f`) before the replay: decline 0.7393 (accuracy 82.7%; Q5 tie-break between two tied ranges), same 0.0573.

**Limitation:** the tuning drafts had no correct+wrong pairs (0 of 60 questions mixed correct and incorrect drafts at k = 15), so the "same" cutoff saw only positives (410 both-correct pairs; any cutoff up to 0.115 scored 100%) and links almost every pair of answering drafts. Recorded, not changed: the frozen rule applied, and condition (b) fails regardless of the cutoff.

Replay on the 200 held-out stage 3 drafts (`agree21_k15`), same decision rule (`pipelines.decide`), draft grades from the original run:

| Grouping | Verified | Verified answers | Verified declines | Correct | Incorrect | Correct given attempted | Unverified guesses | Grouping time (200 q) |
|---|---|---|---|---|---|---|---|---|
| qwen (argo GPU) | 178 | 134 | 44 | 127 | 6 | **95.5%** | 22 | 375 s |
| Laya (argo CPU) | 164 | 146 | 18 | 112 | 13 | **89.6%** | 36 | 421 s |

- (a) rate within 1 point: **fails** (89.6% vs 95.5%, −5.9 points).
- (b) at least 5x faster: **fails** (0.89x; Laya is slower on argo's CPU, 2.1 s/question vs qwen's 1.9 s on the GPU).
- Of Laya's 146 "verified answers", 21 chosen drafts were graded not attempted: its decline detection let declining drafts through as answers.

**Verdict: Laya dropped.** The system stays qwen + Wikipedia + agreement. A reworded or fine-tuned Laya would be a new checker version with its own decisions written in advance (Q4).

### Stage 6 decisions (2026-10-16)

The shipping system after stage 4: stage 2.1 retrieval (title match + normalization, k = 15) + stage 3 agreement (5 drafts, 4-of-5), grouping by qwen.

- **Guesses:** unverified best guesses are shown and labelled, behind a config toggle (`show_guesses`, default true on this instance). When false they become "No reliable answer found".
- **Q1, modes:** two models in Open WebUI. **Verified** (stage 2.1 + agreement, ~90 s, verified/guess label) and **Fast** (stage 2.1 only, ~26 s, labelled "not cross-checked").
- **Q2, follow-ups:** qwen (thinking off) rewrites the latest message into a standalone question using the chat history; the rewrite drives search and drafting and is shown in the progress notes.
- **Q3, non-factual requests:** a qwen check (thinking off) asks whether this is a factual question that can be looked up; if not, plain qwen answers, labelled "not fact-checked". A separate "Plain qwen" model is also offered.
- **Q4, answer layout:** answer; status line (✅ Verified (n/5 drafts agree) / ⚠️ Unverified best guess: drafts disagreed (n/5) / No reliable answer found); Sources (distinct Wikipedia articles among the retrieved passages, linked); stamp "Wikipedia snapshot 2023-11-01" (becomes "as of <date>" when stage 7 brings per-article revision dates).
- **Q5, progress:** streamed as a collapsible `<details>` block at the top of the reply, then the answer. The service stays independent of Open WebUI.
- **Q6, concurrency:** one request runs at a time; waiting requests stream "Queued (n ahead)". **The 10-minute limit starts when a request begins executing, not on arrival.**
- **Q7, logging:** one JSONL line per request in `~/laya-data/service-log/` (rewritten question, mode, route, passages, drafts, decision, timings). Phoenix tracing later, not in stage 6.
- **Q8, ports:** Open WebUI on 3100 and the service on 8100, both bound only to argo's tailnet address (100.108.252.74).

### Stage 6 deployment (2026-10-16)

- `laya-qwen.service` (systemd, user peacekins): uvicorn on 100.108.252.74:8100; config `~/laya-data/service.json` (`show_guesses: true`); request log `~/laya-data/service-log/`.
- `open-webui.service` (systemd wrapping `docker run`): Open WebUI on 100.108.252.74:3100, OpenAI backend = the service, Ollama backend disabled, background tasks (titles, tags) use `qwen-quick`.
- Both units start after tailscaled and retry every 10 s, so they come up once the tailnet address exists after a reboot.
- Smoke test (`scripts/service_smoke.py`) passed: background task, verified answer, follow-up rewrite, non-factual routing, queueing with the limit starting at execution, client disconnect without overlapping runs.
- Noted for later, unchanged: Sources lists every distinct article among the 15 passages (noisy); answers often begin "Based on the provided passages" (from the measured stage 2 prompt).

### Stage 7 corpus-swap evaluation: constraints recorded ahead of the gated design

- **Stratification (Alex, 2026-10-16):** test questions are stratified into table-answerable and prose-answerable. The swap must win the table stratum without losing the prose stratum; an aggregate win that hides a prose regression doesn't count.
- Open for the Oct 30 design round (not decided yet): how a question is assigned to a stratum, where infobox-answerable questions go, what counts as "win" and "not lose" per stratum (thresholds, counts vs rates), stratum sizes, questions answerable from neither corpus, and the request-log findings.

### Stage 7 decisions: dump format and update plumbing (branch `stage7`, 2026-10-16)

- **Q1, frozen corpus untouched:** the new corpus is built in its own database (`~/laya-data/wiki-<date>.db`) with its own source tag (`wikipedia-<date>-html`). The live service and all benchmarks keep `wikipedia-20231101` until the gated swap decision; nothing on the branch changes `main`'s defaults.
- **Q2, tables:** one passage per group of rows, each repeating the table caption, section heading and column headers, rows as "Header: value; …", packed to ~250 words.
- **Q3, infoboxes:** each infobox becomes its own passage ("Infobox: <title>, Field: value; …"), tagged as an infobox.
- **Q4, prose chunking:** unchanged (~250 words), so the Oct 30 comparison isolates the corpus.
- **Q5, update fields:** `articles` gains revision ID, real revision timestamp and passage count; new `corpus_meta` (snapshot date, source format, last update applied) and `update_log` (per-run checkpoints for resume).
- **Q6, live web retrieval:** out of scope for this round; waits for the Oct 30 review with the evaluation method.

Facts (research 2026-10-16): the public Enterprise HTML mirror on dumps.wikimedia.org stopped after 20250320; current Enterprise snapshots need a free account (monthly, on the 1st, 30 snapshot downloads/month). HF `wikimedia/wikipedia` has nothing newer than 20231101; HF `wikimedia/structured-wikipedia` has a May 2026 enwiki snapshot (parsed tables/infoboxes as JSON, rev ID, `date_modified`). EventStreams `mediawiki.page_change.v1` is resumable (`Last-Event-ID` / `since`) with ~7–9 days of retention; page HTML via REST `page/html`. Unauthenticated rate limit 200 req/min with a compliant User-Agent, ≤3 concurrent; ~73k content pages edited per day.

- **Q7, base snapshot:** Enterprise monthly HTML via a free Enterprise account (credentials on argo, readable only by peacekins); one HTML parser for both the base and the daily fetches. HF `structured-wikipedia` is the fallback if the Enterprise route fails.
- **Q8, daily updates:** consume `page_change` for enwiki namespace 0 with a stored resume point; once a day fetch the latest HTML of each changed article (deduplicated, ≤3 concurrent), parse with the same parser, delete the article's passages and insert the new ones; deletions and moves from the same stream. An outage beyond the stream's retention waits for the next monthly rebuild, which also resets drift. **The daily update is never applied in place against the live index: it is applied atomically or in a quiesced window** (mechanism: Q12).
- **Q12, keeping the daily update off the live index:** update a copy, then swap. Each night the live index is copied, the day's changes applied to the copy, the copy verified (Q13), and the `wiki-live.db` symlink switched to it; the service reopens its connection between requests when the target changes. Yesterday's copy is the rollback; the live file is never written.
- **Q13, checks before a swap** (any failure: no swap, yesterday's index stays live, failure written to the update log):
  1. Map consistency: every passage mapped, no orphans, `passage_article` consistent with `articles`.
  2. Every changed article's passages match its newly parsed text exactly.
  3. Article and passage counts moved by no more than the day's changes explain.
  4. A fixed set of 20 probe questions with answers in stable articles still retrieves them.
  5. A sample of the day's changed articles: their new passages are present and findable in the copy's search index (an FTS query on a distinctive phrase from each sampled new passage returns it) before swapping.
- **Q14, what the HTML parser keeps:** prose paragraphs, lists, tables (Q2) and infoboxes (Q3), with section headings as passage context. Dropped: reference lists and citation markers, navboxes, hatnotes, edit links, coordinates, image captions, and the See also / References / External links / Further reading sections.
- **Q15, schedule under the gate:** the first index is built from the latest Enterprise monthly snapshot; the nightly update runs at 03:00 CT against a staging pointer (`wiki-staging.db`), exercising all Q13 checks and the copy-then-swap cycle while the service stays on the 2023 corpus. Monthly rebuilds start after the gate decision.
- **Q16, Enterprise account:** created by the user, credentials placed on argo in `~/laya-data/enterprise.env` (mode 600, peacekins). Meanwhile the parser is built and tested on one shard of the archived 20250320 Enterprise HTML dump (same format).
- **Q9, User-Agent contact:** the project URL `number5alive.com`, not an email.
- **Q10:** unauthenticated access (200 req/min, ~6 h/day); add an authenticated account only if the daily fetch can't finish within a day.
- **Q11, storage:** monthly HTML snapshot on `/mnt/hub/data/wikipedia/enterprise/<date>/` (keep the last 2); indexes on NVMe: live + one rollback, plus the frozen 2023 index until the swap decision.
### Phoenix tracing (2026-10-16; requested by Dan, diagnosed by Alex)

The answering service exports OpenTelemetry traces with OpenInference attributes to Phoenix on argo (OTLP gRPC `http://localhost:4317`, UI on 6006), project **`laya-qwen`**. Phoenix's install and all port bindings are unchanged.

- **Spans per request:** root `answer` (CHAIN) with attributes `laya.mode` (verified / fast / plain), `laya.model_id`, `laya.route`, `laya.decision` (verified / guess / no reliable answer / not cross-checked / not fact-checked), `laya.decision_detail` (the stage 3 decision), `laya.agreement_fraction` (verified mode), input and output. Children:
  - `rewrite_question` (LLM, follow-ups only): original and rewritten question;
  - `route_check` (LLM): the factual-question check;
  - `retrieve` (RETRIEVER): the 15 passages as documents, passage and article counts, corpus stamp, source;
  - `draft` (LLM) ×5 in Verified, ×1 in Fast: model `qwen3.6:27b`, prompt/completion tokens, latency;
  - `agreement` (CHAIN, Verified): agreement fraction, decision, groups;
  - `compose` (CHAIN): the final reply;
  - `plain_answer` (LLM) for plain routes; Open WebUI background tasks appear as separate `background_task` traces.
- **Observation only:** prompts, pipeline logic, modes, response format, queueing, the 10-minute limit and the JSONL log are unchanged (log entry keys identical to the live log's for both modes). Draft spans are recorded after the drafts return, timed from the existing progress callback, so the pipeline code is untouched.
- **Fail-open:** export runs on OpenTelemetry's batch processor thread; every tracing call is wrapped so errors can't reach the answering code; exporter failures are logged once per target. Tested with a dead endpoint: same answer and status, normal time (Fast 51.9 s vs 44.6 s restored, within the usual run-to-run variation; route check 8.6 s vs 7.8 s).
- **Toggle:** `~/laya-data/service.json` → `"phoenix": {"enabled": true, "endpoint": "http://localhost:4317"}`; read per request like `show_guesses`. **To turn tracing off: set `"enabled": false`** (takes effect on the next request, no restart). Changing `endpoint` swaps the exporter on the next request. Absent section = enabled, localhost:4317. The existing `config` field of each JSONL entry records this section along with the rest of service.json.
- **Acceptance (2026-10-16, live service after deploy):**
  1. Verified "Who received the IEEE Frank Rosenblatt Award in 2010?" → ✅ Michio Sugeno (5/5), 85 s; trace `64e1afc2…`: root decision `verified`, agreement fraction 1.0; children route_check, retrieve, 5 draft LLM spans, agreement, compose. (A follow-up question on the pre-deploy test instance showed the `rewrite_question` span with the rewritten question.)
  2. Fast "In what city was the 6th ASEM Education Ministers Meeting held?" → Seoul, 32 s; trace `f47019e7…`: route_check, retrieve, 1 draft, compose.
  3. Fail-open: endpoint set to `http://localhost:4399` (nothing listening), same Fast question → normal answer and status in 27.6 s, one exporter warning in the journal, no trace exported (as expected); config restored to localhost:4317.
  4. This entry.
- **Test traffic in the live JSONL log** (exclude from the Oct 30 review): request ids `bf710ba64fe3`, `98a8594c910d`, `6051a0baa6d3` (2026-10-16, ~17:46–17:50 CDT).
- **Seen in the first traces, not changed:** the route check (11 output tokens) takes ~8–10 s and the rewrite ~17 s, likely Ollama reloading qwen3.6 when calls switch context size (the route check uses the default context, the rest 16,384). A candidate for a separate, measured change.

### Oct 30 readiness push (brief from Alex at Dan's direction, 2026-10-18)

Readiness is plumbing: nothing here changes the live answering service, the live corpus (`wiki.db`, 2023) or the Oct 30 gate, which still owns the request-log review, the corpus-swap evaluation design, every shelf's test design and every adoption decision.

#### Workstream A: stage 7 nightly staging updater (Q8/Q12/Q13/Q15), running from 2026-10-19

- **Code:** `src/laya_qwen/wiki_update.py`; units `deploy/laya-qwen-wiki-update.{service,timer}` (oneshot, Nice 10, best-effort I/O priority 7, 20 h limit). Timer: `OnCalendar=*-*-* 03:00:00 America/Chicago`, `Persistent=true`.
- **One run:**
  1. Read `mediawiki.page_change.v1` from the saved resume point (`?since=`) up to the run's start time, plus a 2-minute margin so both datacenter topics catch up. Catch-up runs at about 50 minutes of stream per 30 s, so a full day takes ~15 min. No always-on listener is needed. The run keeps enwiki namespace 0 and pages moved out of it, last event per page.
  2. Copy the file the `wiki-staging.db` pointer targets to `wiki-staging-<run>.db`. The source must have an empty WAL, and the run checks for free disk ≥ 1.1 × size + 20 GB.
  3. Fetch `rest.php/v1/page/<title>/with_html?redirect=no`: 3 threads, ≤190 req/min, User-Agent `laya-qwen/0.1 (https://number5alive.com)`, retries with backoff on 429/5xx. Parse with the monthly build's parser, then `replace_article(only_if_newer)`; `visibility_change` forces the replace.
     - Deletes, moves out of namespace 0, and pages that became redirects remove the article.
     - A 404 counts as `missing`. A title now owned by another page id counts as `mismatched`.
     - Fetch failures are carried over to the next run.
  4. Run the five Q13 checks on the copy (all must pass):
     - `map_consistency`: `wiki_store.consistency`, a full scan (~14 min on the full index).
     - `changed_articles_exact`: every applied article's passages (text and kind, in order) equal its new parse, and removed articles are gone.
     - `counts_explained`: articles, FTS rows and map rows moved by exactly the applied changes.
     - `probe_questions`: 20 fixed probes (`data/stage7_probes.json`) whose answers sit in stable articles. **Interpretation: the probe check runs the adopted retriever's keyword stage only** (normalised FTS query plus title-matched articles), not the nomic re-rank, so the nightly job never touches the GPU. The probes were frozen after all 20 passed on the 2026-10-01 index; 8 first-draft probes that the keyword stage misses on that index were replaced before freezing. They are a regression canary, not a quality measure.
     - `changed_articles_findable`: 50 sampled articles with new passages. For each, one new passage must be present, and an FTS phrase query on a distinctive 8-token window must return its rowid.
  5. On a full pass, write `update_log` and `corpus_meta` (`last_update_run`, `last_update_position`, `update_stream_start`), checkpoint the WAL, switch the symlink atomically (temporary symlink, then `rename`), advance the resume point, and prune staging copies other than the new target and its rollback.
     - The monthly base `wiki-20261001.db` is never pruned.
     - On any failure: no swap, the resume point stays put, and the copy is kept for diagnosis until the next run.
- **Never** opens `wiki.db` and never touches `laya-qwen.service`. The run lock is `flock`; an overlapping start writes a `skipped_locked` record.
- **Reliability record for the Oct 30 review:** `~/laya-data/stage7-updates/runs.jsonl` holds a `started` line and a result line per run. The result line has:
  - status (`applied`, `failed_checks`, `error`, `skipped_locked`, `test_passed`);
  - window; feed counts by kind;
  - article tallies; passages in and out;
  - all five checks by name with details;
  - per-phase seconds; swap flag; staging target;
  - `live_index_untouched` (size and mtime of `wiki.db` before and after).

  Also kept: per-run text logs `run-<id>.log`, the journal, `state.json` (resume point, rollback, carried-over pages), and `python -m laya_qwen.wiki_update status`.
- **First resume point:** 2026-10-18T14:37:51Z, 24 h before the first run. Changes between the 2026-10-01 snapshot and that point are not applied: they are beyond the feed's ~7-day retention, the Q8 outage case, and wait for the first monthly rebuild after the gate.
- **Tests** (one-chunk index, scratch data dir), four runs:
  - The probe check failed as it should, since a small index lacks the probe articles. There was no swap and the copy was discarded.
  - Three consecutive applied runs swapped and resumed exactly at the previous cutoff. They exercised removal, rollback tracking and pruning.
- **Supervised run 1** (2026-10-19 09:37–15:12 CDT, through the systemd unit): window 2026-10-18T14:37:51Z to 2026-10-19T14:37:51Z.
  - Feed: 1,591,554 events read, 95,390 enwiki namespace-0 events, 58,487 pages (57,890 to fetch, 597 to remove).
  - Articles: 54,830 applied (1,845 created), 157 removed, 81 became redirects, 5 missing, 7 mismatched, 3,407 removals not in the index, 0 fetch errors.
  - Passages: 769,536 in, 748,942 out.
  - Phases: feed 690 s, copy 73 s, fetch/apply 18,406 s, checks 894 s (consistency ~13 min).
  - Checks 1–4 passed (counts moved by exactly +1,607 articles and +20,594 passages).
  - **Check 5 failed on 1 of 50 sampled articles**, so there was no swap and staging stayed on `wiki-20261001.db`, as designed. `wiki.db` was untouched.
  - **Diagnosis: a false failure in the check's implementation, not the index.** The sampled phrase ("competition Columns Club Season League Division League Apps", a footballer's career-statistics table header) matches 190,042 passages. The check read only the first 5,000 ranked matches. A rowid-targeted lookup shows the sampled passages (Mattia Cappelletti, page 83385048) are in the FTS index under that phrase.
  - **Fix (2026-10-19, commit 6ea8de8):** check 5 now asks the FTS index directly whether the phrase matches the sampled passage (`MATCH ? AND rowid = ?`). That is still a query through the copy's search index, now independent of how common the phrase is. Q13 check 5's requirement is unchanged. The fixed check passes on the failed case.
- **Supervised run 2** (started 18:33 CDT, same resume point, window ~33 h): RESULT_PLACEHOLDER

#### Workstream B: maps shelf (geocode / reverse / route / nearby), running from 2026-10-19

- **Packet API:** `src/laya_qwen/maps_api.py`, unit `laya-maps.service`, on **`http://100.108.252.74:8210`** (tailnet only). Backends listen on 127.0.0.1 only.
  - `GET /geocode?q=&state=&near=lat,lon&limit=`. `state` (name or code, or a trailing ", MS" in `q`) is a hard filter: results outside the stated state are dropped, so "Jackson" with Mississippi context can never return Jackson, TN.
  - `GET /reverse?lat=&lon=`: the nearest feature, plus `area` (locality, county, state, state code, nearest locality).
  - `GET /route?from=&to=&profile=car|foot|bike&geometry=`: `from`/`to` take place names or "lat,lon". Returns distance (mi/km), duration, and the corridor: roads carrying ≥3% of the route or ≥5 mi, in order. Named expressways take the route number they are signed with. `geometry` is an optional GeoJSON line of ≤500 points.
  - `GET /nearby?category=&at=&radius_km=&limit=`: about 30 named categories (coffee, fuel, pharmacy, hospital, grocery, hotel, ...) or any OSM `key=value`. Returns named results with distance, address and hours when tagged, and the OSM id.
  - `GET /health`: backend status.
  - Every packet carries `provenance` with the tool, the source and its vintage.
- **Parts:**
  - Geocoder: Photon 1.3.0 (`maps-photon.service`, Temurin 21 container, 4 GB heap, 127.0.0.1:2322) on the GraphHopper Photon USA dump `release-261011`. Import date 2026-10-10T22:59:51Z, read live from `/status`.
  - Router: Valhalla 3.9.1 (`maps-valhalla.service`, 127.0.0.1:8002) on tiles built from `us-latest.osm.pbf`.
  - Nearby: a SQLite R*Tree of 3,001,312 named POIs from the same extract (`maps/build_poi.py`; amenity, shop, tourism, leisure, healthcare, craft and office objects).
- **Extract vintage:** Geofabrik US, replication timestamp 2026-10-15T20:21:00Z (sequence 2413).
- **Placement (approved by Dan, 2026-10-19):** runtime indexes on NVMe under `~/maps-data` (Photon 14 GB, Valhalla tile archive 21 GB, POI db). Sources and archive copies on the hub under `/mnt/hub/data/maps/` (`sources/photon/` dump and jar; `valhalla/` tile archive and config). Build logs are in `~/maps-data/build-logs/`.
- **Deviations:**
  - *Geocoder data (approved by Dan before adoption):* the prebuilt Photon USA dump instead of an index from our extract. Building Photon from our extract needs a full Nominatim US import, which is multi-day and RAM-heavy. Geocode packets therefore carry the Photon vintage; route and nearby packets carry the extract vintage.
  - *Router (the brief's own contingency, "Valhalla only if OSRM hits a wall"):* OSRM 6.0.0 car/MLD was OOM-killed twice in `osrm-extract`'s parsing pass. The first time was at an 18 GB container cap on a routable-ways extract (all highways); the second at a 15 GB cap on a car-only extract (430M nodes, 52M ways before the car filter). Both kills were confined to the build container's cgroup, and no other process was killed. Valhalla builds from disk-backed temporaries and serves a memory-mapped tile archive. One build covers car, foot and bike.
- **Build cost:**
  - Extract copy to NVMe: 19 min (contended hub disk).
  - osmium filters: ~2 min each, 2.5 GB peak.
  - POI index: 113 s.
  - Photon dump download: 10 min. Unpack: ~15 min.
  - **Valhalla tiles: 48 min 37 s wall, 6 threads; tar extract: 71 s.**
  - Peak RAM during the Valhalla build: the container reached its 15 GiB cap as reported by docker, which includes page cache. Host used memory peaked at 16.4 GB. **Host swap was full (8 GB) for ~16 min**, partly left over from the earlier OSRM attempts. There were no OOM kills, and the live service, Open WebUI, Ollama and the updater stayed active.
  - Serving: Photon ~0.45 GB, Valhalla ~0.16 GB resident.
- **Route check amended (Alex, 2026-10-19):** the brief's I-10/I-55 expectation (175–185 mi) was wrong; the network's fastest route is US-49 through Hattiesburg (forcing I-10 west to I-55 gives 244.8 mi / 4h21). Check 2 now reads ~165–175 mi, 2h35–2h50, US-49 corridor. With that correction all five maps checks pass.
- **Acceptance (2026-10-19):** ACCEPTANCE_PLACEHOLDER

#### Workstream C: code reference shelf (brief 2026-10-19), in progress

- **Packet API:** `GET /code/search?q=&source=all|so|docs&tag=&limit=&attribution=` on the maps service (`http://100.108.252.74:8210`, tailnet only), module `src/laya_qwen/code_api.py`.
  - Each result carries source, source label, its own vintage (MDN page commit date, DevDocs package date, Stack Overflow dump date), title, URL, document id, bm25 and full text.
  - It also carries metadata. For Stack Overflow: question id, tags, question score, each answer's score and accepted flag, dates and post URLs. Author names are stored for CC BY-SA attribution and returned with `attribution=true`.
  - Every response lists the sources it searched with their vintages. Search is FTS5 only, with no GPU.
- **Text conversion** (`code_text.py`): every `<pre>` or Markdown code fence becomes its lines indented four spaces. Inline code keeps backticks. Lists, quotes and tables become plain text, and links keep only their text.
- **Docs half, built 2026-10-19:** `~/code-data/code-docs.db` (NVMe), **75,790 passages, 173 MB** against a projected ~0.3 GB, built in 15 s from hub sources.
  - MDN: `mdn/content` blobless clone at `/mnt/hub/data/code/docs/mdn-content`, HEAD `eb950353` (2026-10-19). Covers Web/JavaScript, HTML and CSS: 2,883 pages, 12,766 passages.
    - Pages are split at `##`, and at `###` when a section exceeds 600 words. Titles list the `###` subheadings they contain.
    - Macros become their text, and Specifications, Browser compatibility and See also are dropped.
    - Each passage carries its page's last commit date: 421 distinct dates, 2025-05-14 to 2026-10-18.
  - DevDocs: packages at `/mnt/hub/data/code/docs/devdocs` (`catalogue.json` records each package's release and build date). Python 3.15.0 and 3.14.8, Node 26.3.1, TypeScript 7.0.2, Bash 5.3, Git 2.55.0, SQLite 3.54.0, PostgreSQL 18.6, NumPy 2.5, pandas 3.0.8, Requests 2.34.2, Flask 3.1.1, Django 6.1, Go 1.27.0.
    - Pages are split at headings and at each API entry (each function or class gets its own passage), with long sections split at paragraph boundaries.
    - Rust's package did not finish downloading, so it is skipped for now.
    - The DevDocs Python package is not thin (11,869 passages), so python.org docs are not needed.
  - Refresh is manual (`git pull`, package re-download, rebuild); there is no timer.
- **Q&A half: Stack Overflow, archive.org dump of April 2024** (item `stackexchange`; `communitydatadump.com` does not resolve from argo or the Mac, so the archive.org item it indexes was used directly).
  - `stackoverflow.com-Posts.7z`: 23.0 GB, MD5 7fad5354… verified. `-Users.7z`: 0.99 GB, MD5 verified. Both downloaded at ~30 MiB/s in ~12 min, to `/mnt/hub/data/code/stackexchange/2024-04/`.
  - Scan: 59,819,048 rows (24,101,803 questions, 35,603,624 answers) streamed through `7z x -so` in 476 s. Posts.xml is **not** in Id order (5.9M out-of-order rows), so the extract step looks ids up by binary search.
  - **Filter (ruled by Alex, 2026-10-19):** one passage per question with score ≥ 1 and at least one answer: 10.1M questions, 17.3M answers, ~53 GB projected index (size factor 1.7 × text, to be calibrated). Every question was projected at ~114 GB, over the NVMe budget. The full extraction stays on the hub as the coverage reservoir.
  - Passage: title, body, accepted answer, then up to two more answers by score, each labelled with its score.
  - Extraction (all questions; the filter applies at build time) was interrupted when the hub dropped off USB at 14:37. It restarts when the hub is confirmed back. Builds pause between 02:30 and 03:30 CT.

## Evaluation

- SimpleQA, 200 held-out questions, never used for calibration.
- Grader: qwen3.6 with thinking off, comparing against the gold answer → correct / incorrect / not attempted.
- Also report accuracy split by verified vs labelled-unverified answers.
- Run overnight, unattended.

## Open items

- Stage 6 accepted (2026-10-16). Stage 7 design is on hold for 1–2 weeks (until about 2026-10-30) while the user uses the service; the request log in `~/laya-data/service-log/` will show which corpus gaps are actually hit before the corpus evaluation is designed.
- Stage 7 hold partially lifted (2026-10-16): dump format and update plumbing are designed now, on branch `stage7`. The corpus-swap evaluation method and the swap decision stay gated on the request-log review around 2026-10-30.
- `rev_date` in `articles` is a placeholder (the snapshot date, a floor) until stage 7 loads per-article dates from `stub-meta-current`.
- `~/laya-data/wiki.db.pre-articles` (38 GB) is the index backup taken before the side tables were added; delete it once no longer wanted.
- NVMe space (2026-10-19): the planet tile build was relaunched by another session at 11:23 CDT with its temporaries on NVMe (`~/planet-tmp`). Each nightly staging update needs ~105 GB free for its copy and fails safely (`error`, no swap, resume point kept) if the space is not there. **Resolved from the planet side (Alex, 2026-10-19):** the planet watchdog stops the planet build if NVMe free space is under 130 GB between 02:25 and 02:58, so the 03:00 update gets its space. No updater change.

## The room: one room, two rulesets (added 2026-11-01)

Beside the answering service sits a second body: a room where hosted frontier models do supervised work. It is one room with two rulesets, not two programs. The benches, the seat contract, the task queue, the ledger, the caps, the moderator, and the scribe are shared. The ruleset is data: a ruleset declaration states what circulates, what capability envelope each seat works under, how many rounds may run, and what comes out.

Shared machinery:

- **Queue:** work arrives as self-contained Markdown task files in `queue/`. Each file carries its own brief, its scope header, and its pass marks. The runner (`run-next.sh`) processes one task per invocation; nothing runs in parallel and nothing runs twice.
- **Seat contract:** a seat is invoked through its adapter with a brief, a capability envelope, and a budget. It returns work product and a meter reading. It cannot approve its own reach, and it cannot see the approval records (see Approvals).
- **Ledger:** append-only. Every run writes a planned line before it starts (estimate, caps, scope, approver) and an actual line when it finishes (tokens, cost, exit). Lines are never edited or deleted; corrections are new lines.
- **Budget preflight:** before any run, the machinery checks the task's caps against the session cap, the per-call caps, the reserve, and the monthly ceilings, and refuses the run if the arithmetic fails. Refusal is a normal outcome, not an error.
- **Scribe:** every session is minuted by the scribe function, which files the record (rounds, drafts or positions, standings, outcome) on the local shelves. A record is a record, not an endorsement.

The two rulesets:

- **Factory** (builds): what circulates is an artifact (a website, a harness, a document). Rounds are solo drafting, cross-critique, and merge; recursion happens at the artifact level only, never at the level of model weights. Seats work under the capability envelope the commission names, which may include tools. What comes out is a labelled draft revision with a change record. The Factory never answers questions and never makes standalone decisions.
- **SAINT** (System for Aligned Intelligence and Negotiated Truth; deliberates): what circulates is a question. Seats are tool-stripped: word-only, no shell, no files beyond the brief. What comes out is a decision record: the surviving position, the dissent preserved in the record, and the standings.

Invariants:

- SAINT consensus is agreement, not verification. It never carries Grasshopper's verified stamp, and no mechanism anywhere in the room upgrades agreement into evidence.
- Author and critic default to different benches. A seat never critiques its own draft by default; exceptions must be named in the commission.
- The scribe function never votes. Taking the minutes confers no say in the outcome.
- Johnny may sit in the room in whatever capacities a commission names: seat, scribe, or both at once. Each capacity is labelled in the record, and the scribe function alone never votes even when the same system also sits as a seat.
- The moderator frames the task, distributes the work, tallies, enforces the caps and gates, and reviews the output against pass marks written before the work started. The moderator drafts nothing and votes on nothing.
- Round 0 divergence (a brainstorm round before round 1, in both rulesets) was approved as a structural addition on 2026-11-02. It is not yet built. The current runner has no Round 0 stage; sessions open with the first drafting or proposing round, and any divergence today happens inside that round's briefs.

First worked example: SAINT session 024s1 (2026-11-01), agenda "the next economic system in the world of automation". Claude proposed, Codex challenged, Claude chaired, Johnny scribed and filed the standings. Three rounds, seven frontier calls, $0.3787 against the session cap. The decision record is in `robot-factory/records/`.

## Seats and billing classes

A seat is a mind with a contract. In code it is two things:

- **A registry entry** (`seats/registry.json`): the seat's name, its adapter, its model, its prices (input and output per million tokens, plus any per-call fee), its billing class, its status, and a pointer to its role card.
- **A role card:** what the seat is cast for. The card has two columns of strengths: declared (vendor reputation and the rationale at casting time) and proven (what the seat has actually done well in this room, from the session records). Over time the proven column takes over; casting follows the proven column when the two disagree.

Three adapter shapes cover every current seat:

- **Chat:** ordinary chat completions. The generic core (`seats/api_seat.py`) takes the registry entry and a brief and returns text plus token counts; most API seats are thin wrappers on it.
- **Responses:** the responses shape, built when one vendor retired its chat path mid-setup (task 021). Citations from that seat arrive inline in the answer text.
- **Typed questions:** one seat (Jev) does not chat at all. It answers typed questions (noul, choice, score) with numbers: a probability, a pick, or a fractional position on an ordered scale. Its adapter translates the room's questions into that shape and its answers back into data other seats may cite. It never drafts and never certifies.

Two adapter consequences worth recording. Bare API seats have no clock, so every brief sent to one carries the current date in its text. Subscription seats (the owner's own Claude and ChatGPT plans, driven through their CLIs) are metered in tokens and converted at list prices purely as a quota proxy; the cash cost is zero and the ledger says so by class.

Billing classes:

- **subscription:** usage paced against the plan's allowance, recorded in meter dollars for comparability inside the class only.
- **api:** real dollars, counted against the API ceiling.
- **local:** the on-premises model; free, recorded in tokens, no ceiling but the hardware.

Tallies are kept per class and never summed. A report that added subscription meter dollars to API dollars would be adding a quota proxy to money, so the budget summary prints the classes side by side and stops there. Over the classes sit two ceilings in `budget.yaml`, read at run time: $75 per month across all bodies, and $25 per month for API spending.

Caps: a Factory session reports against $10, a SAINT session against $6.50 (see the worked example below), no session runs more than 3 rounds, and an artifact pauses for review at 20,000 tokens. Per-call caps: frontier seats 60,000 tokens in and 32,000 out; API seats 60,000 in and 8,000 out; the local seat 24,000 in and 4,000 out.

### The overshoot reserve, and why per-call splits matter

The CLI budget flag (`--max-budget-usd`) is not a hard cap: a request already in flight when the cap trips still completes and still bills. The mitigation is mechanical. The seat is handed the session cap minus a reserve, and the reserve is sized to bound one worst-case in-flight request. The reserve was $1.00 while the frontier output cap was 8,000 tokens. When the output cap rose to 32,000 (2026-10-31), the worst case for a single request rose to roughly $1.44 to $1.64 at fitted prices, and on 2026-11-01 the reserve was raised to $2.00 to cover it.

Worked example (task 027, 2026-11-02): the suite re-baseline found every standard SAINT room being refused at preflight. Session planning splits the session cap across the room's frontier calls; at the then SAINT cap of $5.00 over three calls, the per-call cap is $1.66, and preflight refuses any call whose cap does not exceed the reserve. $1.66 does not exceed $2.00, so the room could not start, even though each call itself fit (worst case about $1.64). The reserve raise, correct for single-task Factory runs, had silently interacted with the per-call split in session rooms. The ruling (Dan, 2026-11-02): raise the SAINT session cap to $6.50, which puts the three-call split at $2.16, clear of the reserve, and leaves the reserve discipline unchanged. Lesson recorded with the fix: cap arithmetic must be checked at the smallest split a session can produce, not only at the session level.

## Approvals (tiered, ratified 2026-11-01, built in task 026b)

A task that reads and writes only inside its own work folder is confined and needs no approval. Reach beyond the folder is declared in the task's header (`SCOPE: build-read`, `SCOPE: build-write`, or the legacy `SCOPE: build`) and must be approved before the runner will execute it. An approval is bound to the exact text of the task: the record carries the file's sha256, and the approval's epoch must be newer than the file's modification time. Any edit to the task voids the approval, by hash mismatch or by age, and preflight refuses the run.

Two tiers, split by the kind of reach:

- **build-read:** the seat may read beyond its work folder (other trees on the machine) but writes stay inside the work folder. The moderator may approve this tier. The approval tool (`bin/moderator_approve.py`) appends a record to `approvals-moderator/<task>.jsonl` carrying the hash, the epoch, the approver (`moderator`), and the commission: the owner's instruction the task serves, named in words. Every moderator approval is listed in the budget summary, so the owner can spot-check the whole list at any time.
- **build-write:** any write reach beyond the work folder. This stays with the human, approved interactively at his own terminal through `approve.sh`, which refuses to run without a real terminal, shows the file and its hash, and records the approval the same way. This tier is not delegable. The legacy bare `SCOPE: build` counts as build-write.

Two guards keep the moderator's tier from becoming a hole. First, enforcement during a run: a build-read seat's permission grant enumerates its read paths one by one and excludes `approvals/`, `approvals-moderator/`, and `secrets/` from both reading and writing; edit access exists only inside the work folder; the approval tool itself refuses to run inside a seat run (the runner exports a marker it checks), and preflight reads only the real approvals directory, refusing symlinks and any record lacking the approver and commission fields. Second, the exceptions stay human even on a build-read task: a task carrying a cap override, or marked `APPROVAL: required`, still needs the owner's approval, and the moderator's tool says so when it approves.

Mis-scoping rule (process, not code): if a task approved as build-read turns out to have needed write reach, the tier is presumed suspended pending the owner's review, and every moderator approval is re-listed for spot-checking. There is no suspension switch in the machinery; the rule is recorded here as a standing moderator duty, deliberately, so a future reader does not assume code enforces it.

Note on the first uses: the task that built this tier (026b) could not itself be moderator-approved, since it writes machinery; it ran under the owner's interactive approval, as every machinery change does. The moderator tier was first exercised on 2026-11-02, on a diagnostics task (028) and the code shelf gate task (030).

## Hang glider (fourth mode)

The answering modes converge; hang glider exists to diverge. It is a mode for novel approaches, not for true ones, and its design follows from that single difference. The quirk is a requirement, not a side effect: an architecture built entirely of convergers has no sanctioned way to be strange, so this lane is the licensed eccentric, a little loopy and a little brilliant on purpose. The diversity baseline exists to protect exactly that: a future change that quietly tames the spread is a regression, and it should show as one.

Mechanism:

- **Panel:** five drafts from the bare local model, generated sequentially, not in parallel. Each later draft is briefed with a taken list, the directions the earlier drafts already used, and must go somewhere else. Sequential drafting with a taken list is the anti-repetition mechanism; temperature alone was measured not to be one (in the calibration probes, one prompt produced the same idea five times on heat alone, and nine times across the whole run).
- **Spread:** a wide temperature ladder (0.2, 0.6, 1.0, 1.5, 1.9) combined with angle briefs drawn from a bank (the drafts are written as, for example, a behavioral economist, a game designer, a biologist, a curious twelve-year-old). Heat is the fine knob; the brief is the large knob. A calibration sweep, built behind a flag, pushes the top of the ladder from 2.0 toward 3.0 to find where coherence actually breaks; it has not yet been run against the model, so the cliff is unmeasured and no calibration figures are claimed.
- **Reassessment:** a separate low-temperature pass reads the spread. It names the attractor, the direction the panel converged on, and sets it aside. For each remaining direction it states the mechanism in one line and what the direction ignores. It then applies the selection criterion below and develops the result into the final draft.
- **Selection criterion:** the presented answer is the most new or novel combination of the spread. The reassessor first tries recombination: elements (mechanisms, angles, constraints) from different drafts that no single draft combined, assembled into the most novel combination that still passes a workability check. A combination is presented only if it beats the best single direction on novelty; otherwise the most-different single direction is presented. Parentage is recorded either way: which drafts contributed which elements, so a recombination is never passed off as a raw draft.
- **Output, the five-fold card:** (1) the final draft; (2) a representative conservative pass, (3) a representative middle pass, (4) a representative liberal pass, each representative chosen as nearest its band's center rather than best, and each in a collapsed section under the final draft; (5) the reader's decision. The reader is the fifth element by design: the count of five is preserved with the judge inside it. The full spread and the reassessment reasoning are kept in the run record, one layer down.

Invariants:

- Hang glider carries no stamp of any kind. No label it emits claims verification, convergence, or correctness.
- Selection is permitted here, and only here, because no truth claim is made. Everywhere else in this system, choosing a best answer was rejected as a mechanism: a judge picking a winner manufactures certainty. Triage for novelty, labelled as triage, with the human as the deciding fifth element, does not.
- There is no accuracy gate. In its place: a contract suite checking what can be checked mechanically (the card's shape, exactly three collapsed band sections, the record's completeness, the attractor named, the taken list growing, and the absence of any stamp string in the mode's output path), and a diversity baseline, planned as a frozen battery of prompts whose output spread is kept as the reference, measured by distinct mechanisms per prompt and attractor strength, so a future change that quietly narrows the spread will show against it. The battery has not yet been run.

## Code shelf wiring (second retrieval source)

The code shelf (workstream C above) was built and serving on the packet API (`GET /code/search` on port 8210) from 2026-10-21, but the answering service did not consult it. Wiring it in followed the same discipline as the Wikipedia corpus swap: an audition to choose the mechanism, then a gate with marks written before the run.

- **Scope:** Grasshopper only. The code shelf is a second retrieval source beside Wikipedia in the verified lane. Butterfly and Input are unchanged; Input is bare by definition and never gains shelves.
- **Audition (mechanism choice):** a fixed question set, half API-fact and half debugging, each with a gold passage identified from the shelf and frozen before any run. Two arms on the same questions: plain shelf search, and a librarian arm in which the local model re-ranks the plain arm's candidates. The metric is gold-in-top-3, reported per arm and per question kind. The winning arm becomes the routing mechanism; the audition decides empirically what the router does, rather than the choice being asserted in advance.
- **Gate (run 2026-11-02, task 030b):** the wired lane, simulated before any live change, had to beat the bare model on a held-out code question set by the written margin (+10), clear the written agreed-accuracy floor (80%), and keep a Wikipedia control subset within +/-3 of the Oct 30 gate aggregates. Results: the margin mark FAILED on a saturated set (wired 100.0%, bare 100.0%); the agreed-accuracy mark PASSED (100.0%, 39 agreed); the control mark FAILED (table 80.0%, delta -3.8; prose 100.0%, delta +22.0). Verdict: DO NOT WIRE, recorded unedited in records/030b-code-shelf-gate-record.md. The audition's retrieval stage, scored separately, went the other way: the librarian re-rank won gold-in-top-3 at 62.5% against plain search's 30.0% (n=40), which is the measured basis for the precedence rule below.
- **Override wiring (task 031b, 2026-11-03):** the commissioner wired the shelf anyway, by recorded override, on the ground that the gate showed no evidence of harm, only an absence of certification. The wiring as built: the librarian re-rank of the shelf's top 15 down to 3, behind the environment flag LAYA_CODE_SHELF, read at request time and defaulting off in the source; a 10-second shelf timeout, with any shelf error, timeout, or empty result falling back to the unwired behaviour for that request and the fallback logged; service logs marking shelf-informed runs code_shelf="unverified"; agreement mechanics and the stamp unchanged, since the shelf informs drafts and never votes. Deployment of the staged build to the live service is a separate approval. Certification remains available only through a harder gate.
- **Provenance:** every answer drawn from the code shelf carries its provenance on its face: the source site, the community score, the accepted mark where one exists, and the vintage (April 2024 for the question-and-answer dump; the source name and date for documentation). Community experience is labelled as community experience; it is not dressed as an edited reference.
- **Precedence:** documentation ranks first for API-fact questions, question-and-answer material first for debugging questions, subject to what the audition's per-kind numbers support.

## Interface: the status board and the projection meter


Two interface additions, both read-only by construction.

**The /status endpoint.** The service exposes a status feed whose handler may observe lane state at dispatch time and record it, and may never branch on it: no answering behavior may depend on the feed, so a broken board can never bend an answer. The payload reports which answering lane is executing (or idle), which room session is active if any (read from the Factory's own ledger and session records, tolerating their absence), and the most recent mode and session events with timestamps.

**The board and its lights.** A single self-contained page polls the feed every five seconds and renders six indicator lights: the 5 (the Input lane), the hang glider, the grasshopper, the butterfly, a factory robot (a Factory session is active), and a winged robot (a SAINT session is active). A session lights exactly one robot, chosen by its ruleset. When the feed is unreachable the board degrades to all lights dim with a "no signal" note; it shows stale state as no state, never as current state.

**The projection meter.** Before a session runs, `budget.py project` takes a session plan (ruleset, seats with their roles and call counts, rounds) and prints the run's expected shape. Per seat: an expected figure, taken from the ledger's history as the seat's average actual per comparable call where history exists, and otherwise the per-call cap, labelled cap-bound so the reader knows which kind of number it is; and a worst case, the per-call caps multiplied by the planned calls. Each figure is printed in its billing class's own units: tokens for subscription seats, dollars for API seats, the word "free" for the local seat. Text and JSON output alike keep the classes separate and never produce a summed total. The JSON form carries the plan's ruleset, rounds, and session cap, a per-seat array (seat, roles, calls, billing class, unit, expected, worst case), and the ceilings in force. The board renders the JSON form as per-seat meters (expected against worst case). The meter's own acceptance check is containment: projecting the plan of a recorded session must produce a band that contains that session's recorded actual. Its first containment run (task 033, 2026-11-02) passed and was honestly wide: the recorded SAINT session's plan projected to $0.31-$6.48 against an actual of $0.38. The band is expected to sharpen as the ledger grows; the meter is read-only and writes nothing, ever.
