"""Stage 4: Laya as the draft-grouping checker (replaces qwen's cluster step in a replay).

Two Laya questions:
  - per draft (noul): does the response decline or say the answer is unknown?  (at/above the decline cutoff ->
    declined). The positive phrasing ("does it commit to an answer?") came out inverted on toy examples.
  - per pair of non-declined drafts (choice: same / different): P(same) at/above the same cutoff -> linked; groups
    are the connected components. The noul phrasings scored most different pairs above 0.9 on toy examples.
Phrasings were chosen on 16 hand-written toy examples (no eval or tuning data) before any cutoff tuning.
The cutoffs are tuned on tuning-split drafts labelled from the answer key (DESIGN.md, stage 4 Q3) and frozen
before the replay. Laya runs in-process on CPU, as it would in the final system.
"""

import itertools
import time
from functools import lru_cache

MODEL = ("convaiinnovations/laya", "multilingual")  # 1,024-token input limit
MAX_LEN = 1024

DECLINES_Q = {
    "declines": {
        "type": "noul",
        "instructions": "Does the response decline to answer, or say the answer is unknown or not available?",
    }
}
SAME_Q = {
    "same": {
        "type": "choice",
        "instructions": "Compare the final answers of response A and response B to the question.",
        "criteria": {"same": "They give the same answer", "different": "They give different answers"},
    }
}


@lru_cache(maxsize=1)
def agent():
    import laya

    repo, sub = MODEL
    return laya.load(repo, subfolder=sub, device="cpu")


def scores(question: str, texts: list[str]) -> tuple[list[float], dict[tuple[int, int], float]]:
    """P(declines) per draft and P(same) for every draft pair (all pairs, so cutoffs can be tuned offline)."""
    a = agent()
    res = a.predict_batch([{"question": question, "response": t or "(empty)"} for t in texts], DECLINES_Q,
                          max_len=MAX_LEN)
    declines = [float(r["answers"]["declines"]["noul"]) for r in res]
    pairs = list(itertools.combinations(range(len(texts)), 2))
    states = [{"question": question, "response_a": texts[i] or "(empty)", "response_b": texts[j] or "(empty)"}
              for i, j in pairs]
    res = a.predict_batch(states, SAME_Q, max_len=MAX_LEN) if pairs else []
    same = [float(r["answers"]["same"]["probabilities"]["same"]) for r in res]
    return declines, dict(zip(pairs, same))


def group(declines: list[float], same: dict[tuple[int, int], float], decline_cut: float, same_cut: float):
    """(answers, groups) in the shape pipelines.decide() expects; answers are None for declines."""
    n = len(declines)
    live = [i for i in range(n) if declines[i] < decline_cut]
    parent = {i: i for i in live}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (i, j), p in same.items():
        if i in parent and j in parent and p >= same_cut:
            parent[find(i)] = find(j)
    comps: dict[int, list[int]] = {}
    for i in live:
        comps.setdefault(find(i), []).append(i)
    groups = sorted((sorted(g) for g in comps.values()), key=lambda g: (-len(g), g[0]))
    answers = [None] * n
    for gi, g in enumerate(groups):
        for i in g:
            answers[i] = f"group{gi}"
    return answers, groups


def timed_scores(question: str, texts: list[str]):
    t = time.monotonic()
    out = scores(question, texts)
    return out, time.monotonic() - t
