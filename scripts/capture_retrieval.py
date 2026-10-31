"""Capture top-5 retrieval for the held-out questions, to diff before/after a retrieval refactor.

Works with both the old module-level `retrieval.search` and the `WikiIndexRetriever` interface.
Usage (on argo): OLLAMA_URL=http://localhost:11434 uv run python scripts/capture_retrieval.py out.json
"""

import hashlib
import json
import sys

from laya_qwen import retrieval, simpleqa

if hasattr(retrieval, "WikiIndexRetriever"):
    search = retrieval.WikiIndexRetriever().search
else:
    search = retrieval.search

out = []
for item in simpleqa.heldout():
    hits = search(item.question, k=5)
    out.append({
        "id": item.id,
        "top5": [[p.title, hashlib.sha1(p.text.encode()).hexdigest(), round(p.score, 6)] for p in hits],
        "extra": [[getattr(p, "source", None), getattr(p, "passage_id", None), getattr(p, "page_id", None),
                   getattr(p, "rev_date", None)] for p in hits],
    })
json.dump(out, open(sys.argv[1], "w"))
print(f"captured {len(out)} questions -> {sys.argv[1]}")
