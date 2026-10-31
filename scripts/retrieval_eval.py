"""Stage 2.1 retrieval-only check: is the gold answer in the top 5, per retrieval config?

Dev split only (never the held-out 200). Same sampled questions for every config.
Usage (on argo): OLLAMA_URL=http://localhost:11434 uv run python scripts/retrieval_eval.py N OUT.jsonl
"""

import json
import random
import sys
import time

from laya_qwen import gold_match, simpleqa
from laya_qwen.retrieval import RetrievalConfig, WikiIndexRetriever

CONFIGS = [
    RetrievalConfig(),
    RetrievalConfig(per_article_cap=2),
    RetrievalConfig(expand_titles=True),
    RetrievalConfig(expand_top_articles=2),
    RetrievalConfig(normalize_query=True),
    RetrievalConfig(expand_titles=True, expand_top_articles=2, per_article_cap=2),
    RetrievalConfig(normalize_query=True, expand_titles=True, expand_top_articles=2, per_article_cap=2),
]

n, out_path = int(sys.argv[1]), sys.argv[2]
items = [it for it in random.Random(21).sample(simpleqa.dev(), n * 2) if gold_match.matchable(it.answer)][:n]
summary = {}
with open(out_path, "w") as out:
    for cfg in CONFIGS:
        r = WikiIndexRetriever(config=cfg)
        hit = hit50 = 0
        start = time.monotonic()
        for it in items:
            top = r.search(it.question, k=5)
            ok = any(gold_match.contains(it.answer, p.text) for p in top)
            hit += ok
            out.write(json.dumps({"config": cfg.name(), "id": it.id, "hit": ok,
                                  "articles": len({p.page_id for p in top})}) + "\n")
        secs = (time.monotonic() - start) / len(items)
        summary[cfg.name()] = {"recall@5": round(100 * hit / len(items), 1), "sec_per_q": round(secs, 2)}
        print(cfg.name(), summary[cfg.name()], flush=True)
print(json.dumps({"n": len(items), "results": summary}, indent=1))
