"""Show what retrieval returned for a set of eval rows, and where the gold answer appears.

Usage (on argo): OLLAMA_URL=http://localhost:11434 uv run python scripts/inspect_retrieval.py rows.json
rows.json: list of {"id", "question", "gold", ...} (extra fields such as baseline/rag responses are printed).
"""

import json
import sys

from laya_qwen.retrieval import WikiIndexRetriever


def has(gold: str, text: str) -> bool:
    return gold.lower().strip(".") in text.lower()


r = WikiIndexRetriever()
for x in json.load(open(sys.argv[1])):
    cands = r.keyword_search(x["question"])
    top5 = r.search(x["question"], k=5)
    print("=" * 100)
    print(f"#{x['id']} [{x.get('base_grade')} -> {x.get('rag_grade')}] Q: {x['question']}")
    print(f"GOLD: {x['gold']}")
    if "baseline" in x:
        print(f"BASELINE: {x['baseline'][:250]!r}")
    if "rag" in x:
        print(f"RAG: {x['rag'][:500]!r}")
    print(f"gold string in top-50 keyword candidates at ranks: {[i for i, p in enumerate(cands) if has(x['gold'], p.text)][:10]}")
    print(f"top-50 titles: {sorted({p.title for p in cands})[:25]}")
    for i, p in enumerate(top5, 1):
        mark = "GOLD" if has(x["gold"], p.text) else "    "
        print(f"  {i} {mark} {p.score:.3f} {p.title} :: {p.text[:200]!r}")
