"""Code shelf for the grasshopper lane (task 031b, commissioner's override of the 030b gate).

The code shelf is an UNVERIFIED source. Task 030b's gate verdict was DO NOT WIRE; this wiring ships under the
commissioner's override of 2026-11-03 and nothing here claims the shelf improves answers.

Off unless the environment variable LAYA_CODE_SHELF is "1" at request time. When on, a grasshopper question that
qwen classifies as a programming API-fact or debugging question is answered from code-shelf passages:
shelf top 15 -> local librarian re-rank (030b stage-1 mechanism) picks 3 -> precedence order (docs first for API
facts, Q&A first for debugging) -> the unchanged 5-draft agreement. Any failure raises CodeShelfFallback and the
caller continues on the unwired path.
"""

import concurrent.futures
import json
import os
import time
import urllib.parse

import httpx

from . import ollama, pipelines

SHELF_URL = os.environ.get("LAYA_CODE_SHELF_URL", "http://127.0.0.1:8210")  # test configs may override
SHELF_TIMEOUT = float(os.environ.get("LAYA_CODE_SHELF_TIMEOUT", "10"))  # seconds; 10 is the shipping value
SHELF_K = 15
PICK = 3
QA_VINTAGE = "April 2024 dump"

_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="code-shelf")


class CodeShelfFallback(Exception):
    def __init__(self, reason: str, error: str = ""):
        super().__init__(f"{reason}: {error}" if error else reason)
        self.reason, self.error = reason, error


def enabled() -> bool:
    """Read at request time, so the flag can be set or unset without a code change."""
    return os.environ.get("LAYA_CODE_SHELF") == "1"


# --- which questions use the shelf ------------------------------------------------------------------------------

KIND_PROMPT = """Classify the following message.

- "api": a factual question about a programming language, library, framework, command-line tool, database or \
web API (for example what a function returns, a default value, a parameter, which function or option does something).
- "debug": a question about a programming error, exception, warning or unexpected behaviour of code or a tool.
- "none": anything else, including general-knowledge questions and requests to write or review code.

Message: {question}"""
KIND_SCHEMA = {"type": "object", "properties": {"kind": {"type": "string", "enum": ["api", "debug", "none"]}},
               "required": ["kind"]}


def classify(question: str) -> str:
    r = ollama.chat([{"role": "user", "content": KIND_PROMPT.format(question=question)}], think=False,
                    options={"temperature": 0.0, "num_predict": 20}, format=KIND_SCHEMA)
    kind = json.loads(r.content)["kind"]
    if kind not in ("api", "debug", "none"):
        raise ValueError(f"unexpected kind {kind!r}")
    return kind


# --- shelf search -----------------------------------------------------------------------------------------------


def _get(q: str) -> dict:
    url = f"{SHELF_URL}/code/search?" + urllib.parse.urlencode({"q": q, "source": "all", "limit": SHELF_K})
    r = httpx.get(url, timeout=SHELF_TIMEOUT)
    r.raise_for_status()
    return r.json()


STOPWORDS = frozenset("""a an and are as at be by can could do does for from how i if in into is it its
me my of on or should that the their then there these this to was what when where which who why will with
would you your""".split())
SHELF_QUERY_MAX_TERMS = 3


def _query_terms(question: str) -> str:
    """Reduce a natural-language question to shelf query terms.

    Shelf latency grows with query length (measured 2026-11-03):
    a verbatim question takes ~61 s, five content terms ~12-15 s,
    three terms ~3-8 s. Anything over the 10 s timeout can never
    engage the shelf, so the query is cut to three content words. Content words only, first SHELF_QUERY_MAX_TERMS,
    order preserved, duplicates dropped. Falls back to the raw
    question when nothing survives."""
    words = "".join(ch if ch.isalnum() else " " for ch in question.lower()).split()
    terms: list[str] = []
    for w in words:
        if w not in STOPWORDS and w not in terms:
            terms.append(w)
        if len(terms) >= SHELF_QUERY_MAX_TERMS:
            break
    return " ".join(terms) if terms else question


def search(question: str) -> list[dict]:
    """Shelf top 15. One attempt, hard wall-clock limit of SHELF_TIMEOUT seconds; no retries."""
    fut = _pool.submit(_get, _query_terms(question))
    try:
        data = fut.result(timeout=SHELF_TIMEOUT)
    except concurrent.futures.TimeoutError:
        raise CodeShelfFallback("timeout", f"no shelf response within {SHELF_TIMEOUT:g} s") from None
    except httpx.TimeoutException as e:
        raise CodeShelfFallback("timeout", f"{type(e).__name__}: {e}") from None
    except Exception as e:
        raise CodeShelfFallback("shelf_error", f"{type(e).__name__}: {e}") from None
    results = data.get("results") or []
    if not results:
        raise CodeShelfFallback("empty", "shelf returned no passages")
    return results[:SHELF_K]


# --- librarian re-rank (030b stage 1: prompt, schema and options as run there) ------------------------------------

LIB_PROMPT = """You are a librarian for a programming question-answering system. Below are {n} numbered passages retrieved from programming documentation and Q&A sites, followed by a question.

{passages}

Question: {question}

Choose the 3 passages most useful for answering the question, best first. Reply with their numbers only."""
LIB_SCHEMA = {"type": "object", "properties": {"top3": {"type": "array", "items": {"type": "integer"}}}, "required": ["top3"]}
LIB_OPTIONS = {"temperature": 0.0, "num_ctx": 32768, "num_predict": 200}


def librarian(question: str, passages: list[dict]) -> tuple[list[int], dict]:
    """0-based indices of up to 3 picks, best first."""
    text = "\n\n".join(f"[{i}] {p['title']} ({p['source']})\n{p['text']}" for i, p in enumerate(passages, 1))
    r = ollama.chat([{"role": "user", "content": LIB_PROMPT.format(n=len(passages), passages=text, question=question)}],
                    think=False, options=LIB_OPTIONS, format=LIB_SCHEMA)
    raw = json.loads(r.content).get("top3", [])
    picks = [i for i in dict.fromkeys(raw) if isinstance(i, int) and 1 <= i <= len(passages)][:PICK]
    return [i - 1 for i in picks], {"raw": raw, "seconds": round(r.seconds, 1), "prompt_tokens": r.prompt_eval_count}


def kind_of(p: dict) -> str:
    return "qa" if p.get("source", "").startswith("so:") else "docs"


def precedence(picked: list[dict], question_kind: str) -> list[dict]:
    """Order only (stable): docs first for API-fact questions, Q&A first for debugging questions."""
    first = "docs" if question_kind == "api" else "qa"
    return sorted(picked, key=lambda p: kind_of(p) != first)


def select(question: str, question_kind: str) -> tuple[list[dict], dict]:
    """Shelf top 15 -> librarian top 3 -> precedence order. Raises CodeShelfFallback on any failure."""
    t = time.monotonic()
    results = search(question)
    shelf_seconds = round(time.monotonic() - t, 2)
    try:
        idx, lib = librarian(question, results)
    except Exception as e:
        raise CodeShelfFallback("librarian_error", f"{type(e).__name__}: {e}") from None
    if not idx:
        raise CodeShelfFallback("librarian_error", f"no usable picks in {lib['raw']!r}")
    chosen = precedence([results[i] for i in idx], question_kind)
    meta = {"kind": question_kind, "shelf_seconds": shelf_seconds, "librarian": lib,
            "top15": [{"doc": p.get("doc"), "source": p.get("source"), "bm25": p.get("bm25")} for p in results],
            "librarian_picks": [results[i].get("doc") for i in idx],
            "used": [{"doc": p.get("doc"), "source": p.get("source"), "kind": kind_of(p)} for p in chosen]}
    return chosen, meta


# --- drafts (mirrors pipelines.generate_drafts: same options, n and deadline handling) ---------------------------

CODE_RAG_PROMPT = pipelines.RAG_PROMPT.replace("passages from Wikipedia",
                                               "passages from programming documentation and Q&A sites")


def code_messages(question: str, passages: list[dict]) -> list[dict]:
    text = "\n\n".join(f"[{i}] {p['title']}\n{p['text']}" for i, p in enumerate(passages, 1))
    return [{"role": "user", "content": CODE_RAG_PROMPT.format(passages=text or "(none found)", question=question)}]


def generate_drafts(question: str, passages: list[dict], deadline: float | None = None, on_draft=None):
    opts = {**ollama.THINKING_OPTIONS, "num_ctx": 16384, "num_predict": pipelines.DRAFT_TOKENS}
    msgs = code_messages(question, passages)
    start, drafts = time.monotonic(), []
    for _ in range(pipelines.N_DRAFTS):
        if deadline is not None and drafts and time.monotonic() - start > deadline:
            break
        drafts.append(ollama.chat(msgs, think=True, options=opts))
        if on_draft:
            on_draft(len(drafts), pipelines.N_DRAFTS)
    return drafts


# --- provenance block (rides with the answer) ---------------------------------------------------------------------


def _qa_line(p: dict) -> str:
    m = p.get("meta") or {}
    site = p.get("source", "")[3:]
    bits = [f"Q&A, {site}"]
    if m.get("question_score") is not None:
        bits.append(f"question score {m['question_score']}")
    acc = next((a for a in m.get("answers") or [] if a.get("accepted")), None)
    if acc is not None:
        bits.append(f"accepted answer (score {acc.get('score')})")
    elif m.get("has_accepted") is not None:
        bits.append("accepted answer: " + ("not included" if m.get("has_accepted") else "none"))
    bits.append(QA_VINTAGE)
    return f"- [{p.get('title')}]({p.get('url')}): " + "; ".join(bits)


def _docs_line(p: dict) -> str:
    return f"- [{p.get('title')}]({p.get('url')}): docs, {p.get('source_label') or p.get('source')}"


def provenance_block(passages: list[dict]) -> str:
    lines = [_qa_line(p) if kind_of(p) == "qa" else _docs_line(p) for p in passages]
    return "**Code sources (code shelf, unverified source):**\n" + "\n".join(lines)
