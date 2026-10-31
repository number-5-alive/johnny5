"""Parse an Enterprise HTML NDJSON shard and report passage statistics and speed (stage 7 parser check).
Usage (on argo): uv run python scripts/parse_sample.py SHARD.ndjson [N]"""
import collections, json, random, sys, time
from laya_qwen.html_corpus import parse_article

path, limit = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None
kinds, words, n, t0 = collections.Counter(), collections.Counter(), 0, time.monotonic()
samples, revs = {"table": [], "infobox": []}, collections.Counter()
for line in open(path):
    r = json.loads(line)
    revs[r["identifier"]] += 1
    ps = parse_article(r["name"], r["article_body"]["html"])
    n += 1
    for p in ps:
        kinds[p.kind] += 1
        words[p.kind] += len(p.text.split())
        if p.kind in samples and random.random() < 0.002:
            samples[p.kind].append(p.text[:400])
    if limit and n >= limit:
        break
secs = time.monotonic() - t0
print(json.dumps({"articles": n, "duplicate_page_ids": sum(c > 1 for c in revs.values()), "passages": dict(kinds),
                  "mean_words": {k: round(words[k] / kinds[k]) for k in kinds}, "seconds": round(secs, 1),
                  "articles_per_s": round(n / secs, 1)}))
for k, xs in samples.items():
    for x in xs[:4]:
        print(f"[{k}] {x}")
