"""Check that stage 3 drafts are genuinely diverse before trusting the agreement check.

Uses dev-split questions only (never the held-out 200). For each question it generates the 5 drafts exactly as the
`agree` pipeline does, then reports how different they are. A temperature-0 control on the first questions shows
what "deterministic" looks like, so the comparison means something.

Usage (on argo): OLLAMA_URL=http://localhost:11434 uv run python scripts/draft_diversity.py [N_QUESTIONS]
"""

import itertools
import json
import random
import sys

from laya_qwen import ollama, pipelines, simpleqa

N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
CONTROL = 2


def jaccard(a: str, b: str) -> float:
    x, y = set(a.lower().split()), set(b.lower().split())
    return len(x & y) / len(x | y) if x | y else 1.0


def report(label: str, question: str, drafts) -> dict:
    texts = [d.content for d in drafts]
    thinking = [d.thinking for d in drafts]
    answers, groups = pipelines.cluster(question, texts)
    sims = [jaccard(a, b) for a, b in itertools.combinations(texts, 2)]
    row = {
        "label": label,
        "identical_texts": len(texts) - len(set(texts)),
        "identical_thinking": len(thinking) - len(set(thinking)),
        "mean_word_jaccard": round(sum(sims) / len(sims), 3),
        "distinct_answers": len({a for a in answers if a is not None}) + (1 if None in answers else 0),
        "top_group": len(groups[0]) if groups else 0,
        "declined": sum(a is None for a in answers),
        "answers": answers,
    }
    print(json.dumps(row), flush=True)
    return row


items = random.Random(3).sample(simpleqa.dev(), N)
retriever = pipelines.default_retriever()
rows = []
for k, item in enumerate(items):
    hits = retriever.search(item.question, k=5)
    print(f"\n# Q{k}: {item.question}  (gold: {item.answer})", flush=True)
    rows.append(report("sampled", item.question, pipelines.generate_drafts(item.question, hits)))
    if k < CONTROL:
        greedy = {**ollama.THINKING_OPTIONS, "temperature": 0.0, "num_ctx": 16384, "num_predict": pipelines.DRAFT_TOKENS}
        report("temp0-control", item.question, pipelines.generate_drafts(item.question, hits, options=greedy))

print("\n== summary over sampled drafts ==")
print(f"questions: {len(rows)}")
print(f"questions with any identical draft texts: {sum(r['identical_texts'] > 0 for r in rows)}")
print(f"questions with any identical thinking traces: {sum(r['identical_thinking'] > 0 for r in rows)}")
print(f"mean word-Jaccard between drafts: {sum(r['mean_word_jaccard'] for r in rows) / len(rows):.3f}")
print(f"questions where drafts disagree (top group < 5 incl. declines): {sum(r['top_group'] < 5 and r['declined'] < 5 for r in rows)}")
print(f"questions failing the 4-of-5 agreement: {sum(r['top_group'] < 4 and r['declined'] < 4 for r in rows)}")
