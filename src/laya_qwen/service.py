"""Stage 6: OpenAI-compatible chat service over the shipping pipeline (DESIGN.md, stage 6 decisions).

Models:
  grasshopper  stage 2.1 retrieval (k = 15) + 5-draft agreement; verified / guess / decline label
  butterfly      stage 2.1 retrieval, one answer, labelled "not cross-checked"
  input          qwen3.6 with thinking, no retrieval, labelled "not fact-checked"
  hangglider     bare qwen3.6, 5-draft novelty panel + reassessment, five-fold card, no stamp (hangglider.py)
  qwen-quick          qwen3.6 without thinking, for Open WebUI's background tasks (titles, tags); bypasses the queue

One request runs at a time; waiting requests stream "Queued (n ahead)". The 10-minute limit starts when a request
begins executing. Progress is streamed as a collapsible <details> block, then the answer.

Run (on argo): uv run uvicorn laya_qwen.service:app --host 100.108.252.74 --port 8100
"""

import asyncio
import json
import os
import threading
import time
import uuid
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import code_shelf, hangglider, ollama, pipelines, status_endpoint, tracing

CONFIG_PATH = Path(os.environ.get("LAYA_QWEN_SERVICE_CONFIG", "~/laya-data/service.json")).expanduser()
LOG_DIR = Path(os.environ.get("LAYA_QWEN_SERVICE_LOG", "~/laya-data/service-log")).expanduser()
DEFAULT_CONFIG = {"show_guesses": True}
LIMIT_SECONDS = 600  # per request, counted from the start of execution (not arrival)
GROUPING_RESERVE = 60  # seconds kept back from drafting for grouping and formatting
K = 15
SNAPSHOT_STAMP = "Wikipedia snapshot 2026-10-01"

MODELS = {
    "grasshopper": "Grasshopper (verified): Wikipedia snapshot 2026-10-01 + 5-draft agreement (~90 s)",
    "butterfly": "Butterfly (fast): Wikipedia, one draft, not cross-checked (~26 s)",
    "input": "Input: bare qwen3.6, no retrieval, not fact-checked",
    "hangglider": "Hang glider (novelty): bare qwen3.6, 5-draft spread, most novel direction; no stamp, no truth claim",
    "qwen-quick": "qwen3.6 without thinking, for background tasks",
}
CARD_MODES = {"hangglider"}  # output is a fixed-shape card: no progress or queue <details> block is streamed

REWRITE_PROMPT = """Here is a conversation between a user and an assistant.

{history}

Rewrite the user's last message as a single standalone question that can be understood without the conversation \
(resolve pronouns and references like "he", "it", "that year"). If it is already standalone, return it unchanged. \
Reply with the question only."""

ROUTE_PROMPT = """Is the following a factual question that can be answered by looking information up (for example \
in an encyclopedia), such as who, what, when, where or how many? Requests for code, writing, opinions, advice, \
calculations, or chit-chat are not.

Message: {question}"""
ROUTE_SCHEMA = {"type": "object", "properties": {"factual": {"type": "boolean"}}, "required": ["factual"]}

app = FastAPI(title="laya-qwen")
app.include_router(status_endpoint.router)
_turns: list[str] = []  # request ids waiting or running, in arrival order; index 0 is the one executing
_turn_change = asyncio.Event()
_log_lock = threading.Lock()


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    return cfg


def text_of(content) -> str:
    """OpenAI message content is a string or a list of parts."""
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text")


def clean_messages(messages: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": text_of(m.get("content"))} for m in messages
            if m.get("role") in ("system", "user", "assistant")]


def strip_reply(text: str) -> str:
    """Remove our own progress block and footer from earlier assistant turns before reusing them as history."""
    if text.startswith("<details>") and "</details>" in text:
        text = text.split("</details>", 1)[1]
    return text.split("\n\n---\n", 1)[0].strip()


def log(entry: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _log_lock, (LOG_DIR / f"{date.today().isoformat()}.jsonl").open("a") as f:
        f.write(json.dumps(entry) + "\n")


# --- the work, run in a worker thread; `say` streams a progress note -------------------------------------------


def standalone_question(messages: list[dict], say, entry: dict, tr=None) -> str:
    users = [m for m in messages if m["role"] == "user"]
    last = users[-1]["content"].strip()
    if len(users) == 1:
        return last
    history = "\n\n".join(f"{m['role'].upper()}: {strip_reply(m['content']) if m['role'] == 'assistant' else m['content']}"
                          for m in messages[-8:] if m["role"] in ("user", "assistant"))
    msgs = [{"role": "user", "content": REWRITE_PROMPT.format(history=history)}]
    with tracing.span(tr, "rewrite_question", "LLM") as sp:
        r = ollama.chat(msgs, think=False, options={"temperature": 0.0, "num_ctx": 16384, "num_predict": 200})
        q = r.content.strip().strip('"') or last
        sp.set(**tracing.llm_attrs(ollama.MODEL, msgs, r), laya__original_question=last, laya__rewritten_question=q)
    entry["rewrite_seconds"] = round(r.seconds, 2)
    say(f"Rewritten question: *{q}*")
    return q


def is_factual(question: str, entry: dict, tr=None) -> bool:
    msgs = [{"role": "user", "content": ROUTE_PROMPT.format(question=question)}]
    with tracing.span(tr, "route_check", "LLM") as sp:
        try:
            r = ollama.chat(msgs, think=False, options={"temperature": 0.0, "num_predict": 20}, format=ROUTE_SCHEMA)
            entry["route_seconds"] = round(r.seconds, 2)
            factual = bool(json.loads(r.content)["factual"])
            sp.set(**tracing.llm_attrs(ollama.MODEL, msgs, r), laya__factual=factual)
            return factual
        except Exception as e:  # on doubt, use the fact pipeline: worst case is a decline
            entry["route_error"] = f"{type(e).__name__}: {e}"
            sp.set(laya__route_error=entry["route_error"], laya__factual=True)
            return True


def plain_answer(messages: list[dict], think: bool = True, tr=None) -> str:
    history = [{"role": m["role"], "content": strip_reply(m["content"]) if m["role"] == "assistant" else m["content"]}
               for m in messages]
    opts = {**ollama.THINKING_OPTIONS, "num_ctx": 16384, "num_predict": 12000} if think else {"temperature": 0.7}
    with tracing.span(tr, "plain_answer" if think else "background_task", "LLM") as sp:
        r = ollama.chat(history, think=think, options=opts)
        sp.set(**tracing.llm_attrs(ollama.MODEL, history, r))
    return r.content


def quick_job(messages: list[dict]) -> str:
    """Open WebUI background tasks (titles, tags): one LLM call, traced as its own small trace."""
    return plain_answer(messages, False, tracing.tracer(load_config()))


def sources_block(hits, heading: str = "Sources") -> str:
    seen, lines = set(), []
    for p in hits:
        if p.url in seen:
            continue
        seen.add(p.url)
        lines.append(f"- [{p.title}]({p.url})")
    return f"**{heading}:**\n" + "\n".join(lines) if lines else ""


def footer(status: str, hits=None, heading: str = "Sources") -> str:
    parts = [status]
    if hits:
        parts.append(sources_block(hits, heading))
        parts.append(f"*{SNAPSHOT_STAMP}*")
    return "\n\n---\n" + "\n\n".join(p for p in parts if p)


MODES = {"grasshopper": "verified", "butterfly": "fast", "input": "plain", "hangglider": "novelty"}
OUTCOMES = {"agreed_answer": "verified", "unverified_guess": "guess", "cluster_error": "guess",
            "agreed_decline": "no reliable answer", "all_declined": "no reliable answer", "fast": "not cross-checked",
            "hangglider": "no stamp (novelty triage)"}


def run_job(model: str, messages: list[dict], say, entry: dict, started: float) -> str:
    """One question, traced as a root `answer` span (observation only; the work is _answer)."""
    cfg = load_config()
    entry["config"] = cfg
    tr = tracing.tracer(cfg)
    users = [m for m in messages if m["role"] == "user"]
    with tracing.span(tr, "answer", "CHAIN", laya__model_id=model, laya__mode=MODES.get(model, model),
                      input__value=users[-1]["content"] if users else "") as root:
        trace_info: dict = {}  # values only the trace needs; the JSONL entry stays exactly as before
        text = _answer(model, messages, say, entry, started, cfg, tr, trace_info)
        outcome = OUTCOMES.get(entry.get("decision"), "not fact-checked")
        if outcome == "guess" and not cfg.get("show_guesses", True):
            outcome = "no reliable answer"
        root.set(laya__route=entry.get("route", "plain"), laya__decision=outcome,
                 laya__decision_detail=entry.get("decision"), laya__question=entry.get("question"),
                 laya__agreement_fraction=trace_info.get("agreement_fraction"), output__value=text)
        return text


def _answer(model: str, messages: list[dict], say, entry: dict, started: float, cfg: dict, tr, trace_info: dict) -> str:
    if model == "input":
        return plain_answer(messages, tr=tr) + footer("ℹ️ Plain qwen: not fact-checked")
    if model == "hangglider":  # bare model by design: no routing, no retrieval, no agreement check, no stamp
        request = [m for m in messages if m["role"] == "user"][-1]["content"].strip()
        entry["question"] = request
        with tracing.span(tr, "hangglider", "CHAIN", input__value=request) as sp:
            card, record, path = hangglider.run(request, say)
            sp.set(output__value=card, laya__record=str(path))
        entry.update(route="hangglider", hangglider_record=str(path), decision="hangglider")
        return card

    question = standalone_question(messages, say, entry, tr)
    entry["question"] = question
    if model == "grasshopper" and code_shelf.enabled():  # task 031b; flag off -> this block is skipped entirely
        out = _code_shelf_answer(question, say, entry, started, cfg, tr, trace_info)
        if out is not None:
            return out
    if not is_factual(question, entry, tr):
        entry["route"] = "plain"
        say("Not a lookup question: answering with plain qwen")
        return plain_answer(messages, tr=tr) + footer("ℹ️ Not fact-checked (not a lookup question)")
    entry["route"] = "facts"

    with tracing.span(tr, "retrieve", "RETRIEVER", input__value=question) as sp:
        hits = pipelines.default_retriever(pipelines.adopted_config()).search(question, k=K)
        doc_attrs = {}
        for i, p in enumerate(hits):
            doc_attrs[f"retrieval__documents__{i}__document__id"] = str(p.passage_id)
            doc_attrs[f"retrieval__documents__{i}__document__score"] = round(p.score, 4)
            doc_attrs[f"retrieval__documents__{i}__document__content"] = f"{p.title}: {p.text}"
            doc_attrs[f"retrieval__documents__{i}__document__metadata"] = json.dumps(
                {"title": p.title, "url": p.url, "page_id": p.page_id, "source": p.source})
        sp.set(**doc_attrs, laya__passage_count=len(hits), laya__article_count=len({p.url for p in hits}),
               laya__corpus_stamp=SNAPSHOT_STAMP, laya__source=hits[0].source if hits else None)
    entry["passages"] = pipelines.passages_meta(hits)
    say(f"Retrieved {len(hits)} passages from {len({p.url for p in hits})} Wikipedia articles")

    if model == "butterfly":
        say("Writing the answer")
        msgs = pipelines.rag_messages(question, hits)
        with tracing.span(tr, "draft", "LLM", laya__draft_index=1) as sp:
            r = ollama.chat(msgs, think=True, options={**ollama.THINKING_OPTIONS, "num_ctx": 16384, "num_predict": 12000})
            sp.set(**tracing.llm_attrs(ollama.MODEL, msgs, r))
        entry["decision"] = "fast"
        with tracing.span(tr, "compose", "CHAIN") as sp:
            out = r.content + footer("ℹ️ Fast mode: one answer, not cross-checked", hits)
            sp.set(output__value=out)
        return out

    # Verified: 5 drafts, grouping, stage 3 decision rule.
    budget = LIMIT_SECONDS - (time.monotonic() - started) - GROUPING_RESERVE
    draft_ends, t_drafts = [], tracing.now_ns()

    def on_draft(i, n):
        draft_ends.append(tracing.now_ns())
        say(f"Draft {i}/{n} written")

    drafts = pipelines.generate_drafts(question, hits, deadline=max(budget, 0), on_draft=on_draft)
    msgs = pipelines.rag_messages(question, hits)
    for i, d in enumerate(drafts):  # drafts are timed from the progress callback; spans are recorded afterwards
        start_ns = draft_ends[i - 1] if i > 0 and i - 1 < len(draft_ends) else t_drafts
        end_ns = draft_ends[i] if i < len(draft_ends) else tracing.now_ns()
        tracing.past_llm_span(tr, "draft", start_ns, end_ns, {**tracing.llm_attrs(ollama.MODEL, msgs, d),
                                                               "laya__draft_index": i + 1})
    texts = [d.content for d in drafts]
    if len(drafts) < pipelines.N_DRAFTS:
        say(f"Time limit: stopped after {len(drafts)} drafts")
    say("Comparing drafts")
    with tracing.span(tr, "agreement", "CHAIN", input__value=question) as sp:
        try:
            answers, groups = pipelines.cluster(question, texts)
            failed = False
        except Exception as e:
            answers, groups, failed = [None] * len(texts), [], True
            entry["cluster_error"] = f"{type(e).__name__}: {e}"
        decision, text, verified, chosen = pipelines.decide(texts, answers, groups, failed)
        n, top, declined = len(texts), len(groups[0]) if groups else 0, sum(a is None for a in answers)
        fraction = round((declined if decision in ("agreed_decline", "all_declined") else top) / n, 3) if n else None
        sp.set(laya__decision=decision, laya__agreement_fraction=fraction, laya__drafts=n, laya__top_group=top,
               laya__declined=declined, laya__answers=[a or "(declined)" for a in answers],
               laya__groups=json.dumps(groups), output__value=decision)
    entry.update(drafts=texts, answers=answers, groups=groups, decision=decision, chosen_draft=chosen)
    trace_info["agreement_fraction"] = fraction
    with tracing.span(tr, "compose", "CHAIN") as sp:
        out = _compose(decision, text, texts, chosen, n, top, declined, hits, cfg)
        sp.set(output__value=out)
    return out


def _code_shelf_answer(question: str, say, entry: dict, started: float, cfg: dict, tr, trace_info: dict) -> str | None:
    """Grasshopper over the code shelf (task 031b; UNVERIFIED source, commissioner's override of the 030b gate).

    Returns None to continue on the unwired path: for non-programming questions, and on any shelf error, timeout or
    empty result (recorded in entry["code_shelf_fallback"]). The agreement rule is unchanged; the shelf never votes."""
    try:
        kind = code_shelf.classify(question)
    except Exception as e:
        entry["code_shelf_fallback"] = {"reason": "classify_error", "error": f"{type(e).__name__}: {e}"}
        return None
    if kind == "none":
        return None
    say("Programming question: searching the code shelf (unverified source)")
    try:
        passages, meta = code_shelf.select(question, kind)
    except code_shelf.CodeShelfFallback as e:
        entry["code_shelf_fallback"] = {"reason": e.reason, "error": e.error, "kind": kind}
        say("Code shelf unavailable: using the usual path")
        return None
    except Exception as e:  # never let the shelf fail the request
        entry["code_shelf_fallback"] = {"reason": "shelf_error", "error": f"{type(e).__name__}: {e}", "kind": kind}
        say("Code shelf unavailable: using the usual path")
        return None
    entry["route"] = "code"
    entry["code_shelf"] = "unverified"
    entry["code_shelf_meta"] = meta
    say(f"Using {len(passages)} code-shelf passages chosen by the librarian from the shelf's top {len(meta['top15'])}")

    budget = LIMIT_SECONDS - (time.monotonic() - started) - GROUPING_RESERVE
    drafts = code_shelf.generate_drafts(question, passages, deadline=max(budget, 0),
                                        on_draft=lambda i, n: say(f"Draft {i}/{n} written"))
    texts = [d.content for d in drafts]
    if len(drafts) < pipelines.N_DRAFTS:
        say(f"Time limit: stopped after {len(drafts)} drafts")
    say("Comparing drafts")
    with tracing.span(tr, "agreement", "CHAIN", input__value=question) as sp:
        try:
            answers, groups = pipelines.cluster(question, texts)
            failed = False
        except Exception as e:
            answers, groups, failed = [None] * len(texts), [], True
            entry["cluster_error"] = f"{type(e).__name__}: {e}"
        decision, text, verified, chosen = pipelines.decide(texts, answers, groups, failed)
        n, top, declined = len(texts), len(groups[0]) if groups else 0, sum(a is None for a in answers)
        fraction = round((declined if decision in ("agreed_decline", "all_declined") else top) / n, 3) if n else None
        sp.set(laya__decision=decision, laya__agreement_fraction=fraction, laya__code_shelf="unverified")
    entry.update(drafts=texts, answers=answers, groups=groups, decision=decision, chosen_draft=chosen)
    trace_info["agreement_fraction"] = fraction
    return _compose(decision, text, texts, chosen, n, top, declined, None, cfg) + "\n\n" + code_shelf.provenance_block(passages)


def _compose(decision, text, texts, chosen, n, top, declined, hits, cfg) -> str:
    if decision == "agreed_answer":
        return text + footer(f"✅ Verified ({top}/{n} drafts agree)", hits)
    if decision in ("agreed_decline", "all_declined"):
        return pipelines.DECLINE_TEXT + footer(f"No reliable answer found ({declined}/{n} drafts found no answer)",
                                               hits, "Searched")
    # unverified_guess or cluster_error
    why = "grouping failed" if decision == "cluster_error" else f"drafts disagreed ({top}/{n})"
    if cfg.get("show_guesses", True) and chosen is not None:
        return texts[chosen] + footer(f"⚠️ Unverified best guess: {why}", hits)
    return "No reliable answer found." + footer(f"Drafts disagreed, so no answer is given ({why})", hits, "Searched")


# --- HTTP layer ------------------------------------------------------------------------------------------------


def chunk(rid: str, model: str, content: str | None = None, finish: str | None = None, role: bool = False) -> str:
    delta = {"role": "assistant"} if role else ({"content": content} if content is not None else {})
    body = {"id": rid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(body)}\n\n"


async def _finish_after(fut, rid: str, entry: dict) -> None:
    """Client went away mid-run: hold the turn until the worker thread ends, so runs never overlap."""
    await asyncio.wait([fut])
    entry["finished"] = time.time()
    entry["client_disconnected"] = True
    log(entry)
    if rid in _turns:
        _turns.remove(rid)
    _turn_change.set()


async def produce(model: str, messages: list[dict]):
    """Yields text pieces of the reply: progress notes inside <details>, then the answer."""
    rid = uuid.uuid4().hex[:12]
    entry = {"id": rid, "model": model, "arrived": time.time()}
    loop = asyncio.get_running_loop()

    if model == "qwen-quick":  # Open WebUI background tasks: no queue, no progress block
        entry["started"] = time.time()
        text = await asyncio.to_thread(quick_job, messages)
        entry.update(finished=time.time())
        log(entry)
        yield text
        return

    show_progress = model != "input" and model not in CARD_MODES
    show_queue = model not in CARD_MODES  # a queue block would add a fourth <details> to the card
    opened = False

    def open_block():
        return "<details>\n<summary>Progress</summary>\n\n"

    _turns.append(rid)
    fut = None
    try:
        last_note = 0.0
        while _turns[0] != rid:
            if show_queue and time.monotonic() - last_note > 10:
                if not opened:
                    yield open_block()
                    opened = True
                yield f"- Queued ({_turns.index(rid)} ahead)…\n"
                last_note = time.monotonic()
            _turn_change.clear()
            try:
                await asyncio.wait_for(_turn_change.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

        started = time.monotonic()  # the 10-minute limit counts from here
        entry["started"] = time.time()
        notes: asyncio.Queue = asyncio.Queue()

        def say(msg: str) -> None:
            loop.call_soon_threadsafe(notes.put_nowait, msg)

        fut = loop.run_in_executor(None, status_endpoint.observed(run_job), model, messages, say, entry, started)
        if show_progress and not opened:
            yield open_block()
            opened = True
        while not fut.done() or not notes.empty():
            try:
                msg = await asyncio.wait_for(notes.get(), timeout=1)
                if show_progress:
                    yield f"- {msg}\n"
            except asyncio.TimeoutError:
                continue
        try:
            answer = fut.result()
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
            answer = f"Something went wrong: {type(e).__name__}: {e}"
        entry["finished"] = time.time()
        entry["seconds"] = round(time.monotonic() - started, 1)
        if opened:
            yield f"- Done in {entry['seconds']:.0f} s\n\n</details>\n\n"
        yield answer
    finally:
        if fut is not None and not fut.done():
            asyncio.ensure_future(_finish_after(fut, rid, entry))
        else:
            log(entry)
            if rid in _turns:
                _turns.remove(rid)
            _turn_change.set()


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "laya-qwen", "description": d}
                                       for m, d in MODELS.items()]}


@app.get("/health")
async def health():
    return {"ok": True, "running_or_queued": len(_turns), "config": load_config()}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = body.get("model", "grasshopper")
    if model not in MODELS:
        return JSONResponse({"error": {"message": f"unknown model {model}", "type": "invalid_request_error"}}, 404)
    messages = clean_messages(body.get("messages", []))
    if not any(m["role"] == "user" for m in messages):
        return JSONResponse({"error": {"message": "no user message", "type": "invalid_request_error"}}, 400)
    rid = f"chatcmpl-{uuid.uuid4().hex[:16]}"

    if body.get("stream"):
        async def events():
            yield chunk(rid, model, role=True)
            async for piece in produce(model, messages):
                yield chunk(rid, model, piece)
            yield chunk(rid, model, finish="stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    text = "".join([p async for p in produce(model, messages)])
    return {"id": rid, "object": "chat.completion", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
