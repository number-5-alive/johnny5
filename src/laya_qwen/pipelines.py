"""Answering pipelines, one per design stage. Each takes a question and returns an Answer."""

from dataclasses import dataclass, field

from . import ollama


@dataclass
class Answer:
    text: str
    # True = verified, False = labelled unverified guess, None = pipeline doesn't verify.
    verified: bool | None = None
    meta: dict = field(default_factory=dict)


def baseline(question: str) -> Answer:
    """Stage 1: qwen3.6 alone, thinking on, no retrieval or checking."""
    r = ollama.chat(
        [{"role": "user", "content": question}],
        think=True,
        options={**ollama.THINKING_OPTIONS, "num_ctx": 16384, "num_predict": 12000},
    )
    return Answer(
        text=r.content,
        meta={
            "seconds": round(r.seconds, 1),
            "eval_tokens": r.eval_count,
            "thinking_chars": len(r.thinking),
            "done_reason": r.done_reason,
        },
    )


RAG_PROMPT = """Here are passages from Wikipedia that may be relevant:

{passages}

Question: {question}

Use the passages where they are relevant. Answer the question directly."""


_retrievers: dict = {}


def default_retriever(config=None):
    """Stage 2 retriever by default; pass a RetrievalConfig for other variants. Cached per config."""
    from .retrieval import STAGE2, WikiIndexRetriever  # needs the index, which only exists on argo

    config = config or STAGE2
    if config not in _retrievers:
        _retrievers[config] = WikiIndexRetriever(config=config)
    return _retrievers[config]


def adopted_config():
    """Stage 2.1 permanent fixes: title match + query normalization (never lost a question on 500 dev)."""
    from .retrieval import RetrievalConfig

    return RetrievalConfig(normalize_query=True, expand_titles=True)


def rag_messages(question: str, hits) -> list[dict]:
    passages = "\n\n".join(f"[{i}] {p.title}\n{p.text}" for i, p in enumerate(hits, 1))
    return [{"role": "user", "content": RAG_PROMPT.format(passages=passages or "(none found)", question=question)}]


def passages_meta(hits) -> dict:
    return {
        "titles": [p.title for p in hits],
        "passages": [
            {"id": p.passage_id, "page_id": p.page_id, "source": p.source, "score": round(p.score, 4)} for p in hits
        ],
    }


def rag(question: str, k: int = 5, config=None) -> Answer:
    """Stage 2: retrieve Wikipedia passages, then qwen3.6 answers with them in context."""
    hits = default_retriever(config).search(question, k=k)
    r = ollama.chat(
        rag_messages(question, hits),
        think=True,
        options={**ollama.THINKING_OPTIONS, "num_ctx": 16384, "num_predict": 12000},
    )
    return Answer(
        text=r.content,
        meta={
            "seconds": round(r.seconds, 1),
            "eval_tokens": r.eval_count,
            "thinking_chars": len(r.thinking),
            "done_reason": r.done_reason,
            **passages_meta(hits),
        },
    )


# Stage 3: agreement check across independent drafts.
N_DRAFTS = 5
AGREE = 4  # drafts that must share an answer (or a refusal) for it to count as verified
DRAFT_TOKENS = 3000  # thinking + answer per draft; ~97% of stage 2 answers fit
DRAFT_DEADLINE = 480  # seconds; stop drafting and decide with what we have (10-minute budget overall)

CLUSTER_PROMPT = """Question: {question}

Below are {n} independent responses to this question.

{responses}

For each response, extract the short final answer it commits to (a name, date, number or short phrase). Use null if the response declines, says the information is unavailable, or doesn't commit to an answer.
Then group the responses whose extracted answers mean the same thing (same entity or value, ignoring wording, formatting and extra detail). Every response with a non-null answer must be in exactly one group; use 0-based response indices."""

CLUSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {"type": "array", "items": {"type": ["string", "null"]}},
        "groups": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
    },
    "required": ["answers", "groups"],
}

DECLINE_TEXT = "I couldn't find a reliable answer to this question in the available sources."
UNVERIFIED_PREFIX = "Unverified best guess (independent drafts disagreed): "


def generate_drafts(question: str, hits, n: int = N_DRAFTS, options: dict | None = None, deadline: float | None = None,
                    on_draft=None):
    """Independent drafts from the same passages. Sampling (temperature 1.0, top_p 0.95, top_k 20, no seed)
    is what makes them independent; Ollama runs qwen3.6 one request at a time, so they are sequential."""
    import time

    opts = options or {**ollama.THINKING_OPTIONS, "num_ctx": 16384, "num_predict": DRAFT_TOKENS}
    start = time.monotonic()
    drafts = []
    for _ in range(n):
        if deadline is not None and drafts and time.monotonic() - start > deadline:
            break
        drafts.append(ollama.chat(rag_messages(question, hits), think=True, options=opts))
        if on_draft:
            on_draft(len(drafts), n)
    return drafts


def cluster(question: str, texts: list[str]) -> tuple[list[str | None], list[list[int]]]:
    """qwen (thinking off) extracts each draft's short answer and groups equivalent ones."""
    import json

    responses = "\n\n".join(f"Response {i}:\n{t or '(empty)'}" for i, t in enumerate(texts))
    r = ollama.chat(
        [{"role": "user", "content": CLUSTER_PROMPT.format(question=question, n=len(texts), responses=responses)}],
        think=False,
        options={**ollama.GRADER_OPTIONS, "num_ctx": 16384, "num_predict": 1000},
        format=CLUSTER_SCHEMA,
    )
    data = json.loads(r.content)
    answers = (list(data["answers"]) + [None] * len(texts))[: len(texts)]
    # Keep only valid, non-null indices, each in one group; anything left over becomes its own group.
    seen: set[int] = set()
    groups = []
    for g in data["groups"]:
        g = [i for i in dict.fromkeys(g) if 0 <= i < len(texts) and answers[i] is not None and i not in seen]
        seen.update(g)
        if g:
            groups.append(g)
    groups += [[i] for i, a in enumerate(answers) if a is not None and i not in seen]
    return answers, sorted(groups, key=lambda g: (-len(g), g[0]))


def decide(texts: list[str], answers: list[str | None], groups: list[list[int]], cluster_failed: bool = False):
    """Stage 3 decision rule, shared by the pipeline and any grouping replay (stage 4).

    Returns (decision, text, verified, chosen_draft) where chosen_draft is the index of the draft whose text is
    returned, or None for a decline."""
    declined = sum(a is None for a in answers)
    top = groups[0] if groups else []
    if cluster_failed:
        first = next((i for i, t in enumerate(texts) if t), None)
        if first is None:
            return "cluster_error", DECLINE_TEXT, False, None
        return "cluster_error", UNVERIFIED_PREFIX + texts[first], False, first
    if len(top) >= AGREE:
        return "agreed_answer", texts[top[0]], True, top[0]
    if declined >= AGREE or not top:
        return ("agreed_decline" if declined >= AGREE else "all_declined"), DECLINE_TEXT, True, None
    return "unverified_guess", UNVERIFIED_PREFIX + texts[top[0]], False, top[0]


def agree(question: str, k: int = 5, config=None) -> Answer:
    """Stage 3: retrieval (as stage 2) + 5 sampled drafts; verified only if 4 of 5 agree."""
    import time

    start = time.monotonic()
    hits = default_retriever(config).search(question, k=k)
    drafts = generate_drafts(question, hits, deadline=DRAFT_DEADLINE)
    texts = [d.content for d in drafts]
    meta = {
        "drafts": len(drafts),
        "draft_tokens": [d.eval_count for d in drafts],
        "draft_done": [d.done_reason for d in drafts],
        "draft_texts": texts,  # kept so the grouping can be replayed by another checker (stage 4)
        **passages_meta(hits),
    }
    t0 = time.monotonic()
    try:
        answers, groups = cluster(question, texts)
    except Exception as e:  # unparseable clustering: fall back to an unverified guess
        answers, groups = [None] * len(texts), []
        meta["cluster_error"] = f"{type(e).__name__}: {e}"
    meta["cluster_seconds"] = round(time.monotonic() - t0, 3)
    meta.update(answers=answers, groups=groups, declined=sum(a is None for a in answers))

    decision, text, verified, chosen = decide(texts, answers, groups, "cluster_error" in meta)
    meta.update(decision=decision, chosen_draft=chosen, seconds=round(time.monotonic() - start, 1))
    return Answer(text=text, verified=verified, meta=meta)


PIPELINES = {"baseline": baseline, "rag": rag, "agree": agree}
# Stage 2.1 variants: adopted retrieval fixes at different k (passages given to qwen).
for _k in (5, 10, 15, 20):
    PIPELINES[f"rag21_k{_k}"] = lambda q, _k=_k: rag(q, k=_k, config=adopted_config())
    PIPELINES[f"agree21_k{_k}"] = lambda q, _k=_k: agree(q, k=_k, config=adopted_config())
