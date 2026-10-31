"""Stage 4: tune Laya's two grouping cutoffs on tuning-split drafts, then replay grouping on the held-out drafts.

  score   RUN OUT.jsonl     Laya scores for every draft and draft pair of a stage 3 run (timed, CPU)
  tune    SCORES.jsonl RUN  fit the cutoffs from answer-key labels (DESIGN.md stage 4 Q3) -> results/stage4_cutoffs.json
  replay  SCORES.jsonl RUN  apply the frozen cutoffs, replay the stage 3 decision rule, compare with qwen (Q2)

RUN is a results/<run>/answers.jsonl produced by an agree* pipeline (draft_texts and draft_grades in meta).
Run `score` on argo (the hardware Laya would run on in the final system).
"""

import json
import sys
import time
from pathlib import Path

from laya_qwen import laya_group, pipelines

RESULTS = Path(__file__).resolve().parents[1] / "results"
CUTOFFS = RESULTS / "stage4_cutoffs.json"


def rows(run: str) -> list[dict]:
    latest = {}
    for line in (RESULTS / run / "answers.jsonl").read_text().splitlines():
        r = json.loads(line)
        latest[r["id"]] = r
    return [r for r in latest.values() if r["grade"] != "error" and "draft_texts" in r.get("meta", {})]


def cmd_score(run: str, out: str) -> None:
    t = time.monotonic()
    laya_group.agent()
    load = time.monotonic() - t
    total = 0.0
    with open(out, "w") as f:
        for r in rows(run):
            (declines, same), secs = laya_group.timed_scores(r["question"], r["meta"]["draft_texts"])
            total += secs
            f.write(json.dumps({"id": r["id"], "declines": declines, "same": [[i, j, p] for (i, j), p in same.items()],
                                "seconds": secs}) + "\n")
    print(json.dumps({"run": run, "questions": len(rows(run)), "laya_load_seconds": round(load, 1),
                      "laya_scoring_seconds": round(total, 2)}))


def load_scores(path: str) -> dict:
    out = {}
    for line in Path(path).read_text().splitlines():
        s = json.loads(line)
        out[s["id"]] = (s["declines"], {(i, j): p for i, j, p in s["same"]}, s["seconds"])
    return out


def best_cut(points: list[tuple[float, bool]]) -> dict:
    """Cutoff c predicts True when score >= c. Accuracy is constant between consecutive distinct scores, so every
    gap is tried. Tied best regions are merged into contiguous ranges; per DESIGN.md stage 4 Q3/Q5 the cutoff is the
    midpoint of the widest tied range (several equally widest: the highest of them), and it must itself achieve the
    best accuracy."""
    scores = sorted({p for p, _ in points})
    bounds = [0.0] + scores + [1.0]
    regions = []  # any c in (lo, hi] gives the same predictions
    for lo, hi in zip(bounds, bounds[1:]):
        if hi <= lo:
            continue
        acc = sum((p >= (lo + hi) / 2) == y for p, y in points) / len(points)
        regions.append([lo, hi, acc])
    top = max(acc for _, _, acc in regions)
    ranges: list[list[float]] = []
    for lo, hi, acc in regions:
        if acc != top:
            continue
        if ranges and ranges[-1][1] == lo:
            ranges[-1][1] = hi  # contiguous with the previous tied region
        else:
            ranges.append([lo, hi])
    lo, hi = max(ranges, key=lambda r: (round(r[1] - r[0], 9), r[0]))  # widest; ties -> highest (width rounded so float noise cannot break a tie)
    cut = (lo + hi) / 2
    assert sum((p >= cut) == y for p, y in points) / len(points) == top, "chosen cutoff must achieve best accuracy"
    return {"cut": round(cut, 6), "accuracy": round(top, 4), "chosen_range": [lo, hi], "tied_ranges": ranges,
            "n": len(points), "positives": sum(y for _, y in points)}


def cmd_tune(scores_path: str, run: str) -> None:
    sc = load_scores(scores_path)
    decline_pts, same_pts = [], []
    for r in rows(run):
        declines, same, _ = sc[r["id"]]
        grades = r["meta"]["draft_grades"]
        decline_pts += [(p, g == "not_attempted") for p, g in zip(declines, grades)]
        for (i, j), p in same.items():
            gi, gj = grades[i], grades[j]
            if gi == gj == "correct":
                same_pts.append((p, True))
            elif {gi, gj} == {"correct", "incorrect"}:
                same_pts.append((p, False))
            # both-wrong and pairs with a not-attempted draft are excluded (Q3)
    result = {"tuning_run": run, "decline": best_cut(decline_pts), "same": best_cut(same_pts)}
    CUTOFFS.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


def summarize(decisions: list[tuple[str, int | None, list[str]]]) -> dict:
    """decisions: (decision, chosen_draft, draft_grades). Verified = agreed answers + agreed declines."""
    verified = [(d, c, g) for d, c, g in decisions if d in ("agreed_answer", "agreed_decline", "all_declined")]
    answered = [g[c] for d, c, g in verified if d == "agreed_answer"]
    correct, incorrect = answered.count("correct"), answered.count("incorrect")
    return {"verified": len(verified), "verified_answers": len(answered), "verified_declines": len(verified) - len(answered),
            "correct": correct, "incorrect": incorrect,
            "correct_given_attempted": round(100 * correct / (correct + incorrect), 2) if correct + incorrect else None,
            "unverified_guesses": sum(d == "unverified_guess" for d, _, _ in decisions)}


def cmd_replay(scores_path: str, run: str) -> None:
    cut = json.loads(CUTOFFS.read_text())
    dc, sc_ = cut["decline"]["cut"], cut["same"]["cut"]
    sc = load_scores(scores_path)
    qwen, laya = [], []
    qwen_secs = laya_secs = 0.0
    for r in rows(run):
        m = r["meta"]
        texts, grades = m["draft_texts"], m["draft_grades"]
        qwen.append((m["decision"], m.get("chosen_draft"), grades))
        qwen_secs += m["cluster_seconds"]
        declines, same, secs = sc[r["id"]]
        laya_secs += secs
        answers, groups = laya_group.group(declines, same, dc, sc_)
        d, _, _, chosen = pipelines.decide(texts, answers, groups)
        laya.append((d, chosen, grades))
    q, l = summarize(qwen), summarize(laya)
    speedup = qwen_secs / laya_secs if laya_secs else float("inf")
    a_ok = q["correct_given_attempted"] is not None and l["correct_given_attempted"] is not None and \
        l["correct_given_attempted"] >= q["correct_given_attempted"] - 1.0
    b_ok = speedup >= 5.0
    print(json.dumps({"run": run, "cutoffs": {"decline": dc, "same": sc_}, "qwen": q, "laya": l,
                      "grouping_seconds": {"qwen_gpu": round(qwen_secs, 1), "laya_cpu": round(laya_secs, 1),
                                           "speedup": round(speedup, 2)},
                      "rule": {"a_rate_within_1pt": a_ok, "b_5x_faster": b_ok,
                               "verdict": "LAYA WINS" if a_ok and b_ok else "LAYA DROPPED"}}, indent=1))


if __name__ == "__main__":
    cmd, *a = sys.argv[1:]
    {"score": cmd_score, "tune": cmd_tune, "replay": cmd_replay}[cmd](*a)
