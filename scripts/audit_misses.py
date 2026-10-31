"""Evidence for hand-auditing questions whose gold answer is missing from the keyword top 200.

For each miss: where else the gold wording appears in the corpus, and the passages of the question's likely
articles that share the most question keywords, so a person can judge "not in Wikipedia" vs
"present but worded differently" vs "present verbatim but not retrieved".
Usage (on argo): uv run python scripts/audit_misses.py N_MISSES
"""

import random
import re
import sys

from laya_qwen import gold_match, simpleqa
from laya_qwen.retrieval import RetrievalConfig, STOPWORDS, WikiIndexRetriever, fts_query

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
r = WikiIndexRetriever(config=RetrievalConfig(expand_titles=True))
db = r._db()
items = [it for it in random.Random(21).sample(simpleqa.dev(), 1000) if gold_match.matchable(it.answer)][:500]
random.Random(5).shuffle(items)

found = 0
for it in items:
    rows = db.execute(
        "SELECT text FROM passages WHERE passages MATCH ? ORDER BY bm25(passages, 5.0, 0.0, 1.0) LIMIT 200",
        (fts_query(it.question),),
    ).fetchall()
    if any(gold_match.contains(it.answer, t) for (t,) in rows):
        continue
    found += 1
    keywords = [w for w in re.findall(r"[\w'-]+", it.question.lower()) if w not in STOPWORDS and len(w) > 2]
    print("=" * 110)
    print(f"[{found}] #{it.id} Q: {it.question}\n    GOLD: {it.answer}")
    # 1. Gold wording anywhere in the corpus, ranked by overlap with question keywords.
    hits = []
    for v in gold_match.variants(it.answer):
        phrase = '"' + " ".join(re.findall(r"\w+", v)) + '"'
        try:
            hits += db.execute("SELECT title, text FROM passages WHERE passages MATCH ? LIMIT 300", (phrase,)).fetchall()
        except Exception:
            pass
    scored = sorted(hits, key=lambda h: -sum(k in (h[0] + " " + h[1]).lower() for k in keywords))[:3]
    print(f"    gold wording appears in {len(hits)} passages; best keyword overlap:")
    for title, text in scored:
        m = next((re.search(re.escape(v), gold_match.norm(text)) for v in gold_match.variants(it.answer)
                  if re.search(re.escape(v), gold_match.norm(text))), None)
        t = gold_match.norm(text)
        snip = t[max(0, m.start() - 160): m.end() + 80] if m else t[:200]
        print(f"      - [{title}] (overlap {sum(k in (title + ' ' + text).lower() for k in keywords)}/{len(keywords)}) ...{snip}...")
    # 2. Likely articles (title spans in the question, else the top keyword article) and their best passages.
    pids = r.title_matches(it.question)
    if not pids and rows:
        top = db.execute(
            "SELECT pa.page_id FROM passages p JOIN passage_article pa ON pa.passage_rowid = p.rowid "
            "WHERE passages MATCH ? ORDER BY bm25(passages, 5.0, 0.0, 1.0) LIMIT 1", (fts_query(it.question),)
        ).fetchone()
        pids = [top[0]] if top else []
    for pid in pids[:2]:
        ps = r.article_passages(pid)
        best = sorted(ps, key=lambda p: -sum(k in p.text.lower() for k in keywords))[:2]
        print(f"    likely article: {ps[0].title if ps else pid} ({len(ps)} passages)")
        for p in best:
            print(f"      > {p.text[:450]}")
    if found >= N:
        break
