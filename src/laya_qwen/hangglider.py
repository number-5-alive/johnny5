"""Hang glider: the fourth answering mode (029 prototype; calibration TRY, not a gate).

Promise: not the best answer, the most novel direction. A deliberate counter-collapse instrument: five bare-model
drafts are spread across a temperature ladder and an angle bank, each later draft told which directions are already
taken; a separate low-temperature reassessment names the attractor (the conservative consensus), sets it aside,
clusters the rest, and selects or recombines for novelty, then develops the pick.

The output is the five-fold card: the developed pick on top, labelled "hang glider" and nothing else, then three
representative raw passes (conservative / middle / liberal), each in a collapsed <details> section. The reader is the
fifth element. The mode carries NO stamp and makes no truth claim. It is bare-model by design: no retrieval, no
agreement check, nothing from the verified lane.

Calibration sweep: HANGGLIDER_SWEEP=1 replaces the ladder's TOP temperature with 2.0, 2.25, 2.5, 2.75, 3.0 in turn,
one step per run (the step counter persists in the records directory). Off by default.
"""

import json
import math
import os
import re
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import ollama

LABEL = "hang glider"
LADDER = [0.2, 0.6, 1.0, 1.5, 1.9]
BANDS = {"conservative": (0, 1), "middle": (2,), "liberal": (3, 4)}  # indices into the ladder
SWEEP_TOPS = [2.0, 2.25, 2.5, 2.75, 3.0]
REASSESS_TEMPERATURE = 0.3
DRAFT_TOKENS = 400  # brief: ~220-400 tokens per draft; the prompt asks for ~250 words, this is the hard ceiling
REASSESS_TOKENS = 3000
RECORDS_DEFAULT = "~/laya-data/hangglider-records"


def records_root() -> Path:
    """Read HANGGLIDER_RECORDS at call time, not import time, so an env set after import still governs."""
    return Path(os.environ.get("HANGGLIDER_RECORDS", RECORDS_DEFAULT)).expanduser()

# Stamp strings used elsewhere in Johnny (grasshopper's verified footer in service._compose; the no-malfunction
# prototype's STAMP in work/025-ladder-gate/nomalfunction.py). Neither may appear in hang glider's output (hard
# boundary). This tuple is used ONLY as a filter pattern by defang(); it is never emitted.
FORBIDDEN_STAMPS = ("✅ Verified", "no malfunction")

# The angle bank: drafts draw from it in order, cycling if the panel ever widens past its length.
ANGLE_BANK = [
    {"seat": "behavioral economist",
     "brief": "Approach this as a behavioral economist: look for the incentives, defaults, frictions and "
              "predictable irrationalities at work, and design around how people actually behave."},
    {"seat": "game designer",
     "brief": "Approach this as a game designer: find the loop, the rules, the reward and the moment of play, "
              "and ask what would make someone want to take the next turn."},
    {"seat": "biologist",
     "brief": "Approach this as a biologist: treat it as an organism in an ecosystem, and look for adaptation, "
              "niches, symbiosis, metabolism and what survives selection pressure."},
    {"seat": "curious 12-year-old",
     "brief": "Approach this as a curious 12-year-old: ask the obvious question adults skip, take nothing as "
              "given, and follow whatever seems most fun or most weird."},
    {"seat": "cheerful con artist",
     "brief": "Approach this as a cheerful con artist who has gone straight: you know how attention, trust and "
              "persuasion really work, and you use that know-how openly and honestly."},
    {"seat": "retired circus ringmaster",
     "brief": "Approach this as a retired circus ringmaster: think in spectacle, timing, the crowd, the act "
              "nobody expects, and how a show keeps moving from town to town."},
    {"seat": "mycologist",
     "brief": "Approach this as a mycologist: think in hidden networks, decomposition and regrowth, slow spread "
              "underground, and what fruits only when the conditions are right."},
]

DRAFT_PROMPT = """{angle}

Request: {request}
{taken}
Write one answer of about 150-250 words that commits to a single clear direction. Do not survey options; develop \
one idea. On the very last line, write "Direction:" followed by a one-line summary (at most 20 words) of the \
direction you took."""

TAKEN_BLOCK = """
Directions already taken by earlier drafts (one per line):
{lines}
Go somewhere else: do not repeat, extend or lightly vary any of these directions. Find a genuinely different one.
"""

REASSESS_PROMPT = """You are the reassessor for a novelty panel. Five drafts below answered the same request, each \
from a different angle and temperature. Your job is TRIAGE FOR NOVELTY, not a judgment of truth: you are looking for \
the most new direction, not the most correct one.

Request: {request}

{drafts}

Do the following, in order, and return JSON matching the schema:
1. attractor: name the ATTRACTOR, the direction the panel converged on (the conservative consensus, the answer \
anyone would give). set_aside: one sentence that explicitly sets the attractor aside, beginning "Set aside:".
2. clusters: cluster the remaining directions. For each cluster give the draft numbers, a one-line MECHANISM (how the \
direction works) and what it IGNORES.
3. recombination: identify elements (mechanisms, angles, constraints) from DIFFERENT drafts that no single draft \
combined, and assemble the most novel combination that still passes a workability sniff test. Say whether it is \
workable and whether it beats the best single direction on novelty.
4. best_single: the single draft whose mechanism differs most from the attractor.
5. decision: "combination" only if the combination is workable AND beats best_single on novelty; otherwise "single".
6. pick: the chosen mechanism in one line, what it ignores, why it survived, and its PARENTAGE: which draft \
contributed which element (for a single pick, that one draft and what it contributed).
7. final_draft: develop the pick into a finished answer to the request, about 200-350 words, written to the person \
who asked. Do not mention drafts, panels, attractors or this process; do not claim it is verified or correct."""

REASSESS_SCHEMA = {
    "type": "object",
    "properties": {
        "attractor": {"type": "string"},
        "set_aside": {"type": "string"},
        "clusters": {"type": "array", "items": {"type": "object", "properties": {
            "drafts": {"type": "array", "items": {"type": "integer"}},
            "mechanism": {"type": "string"}, "ignores": {"type": "string"}},
            "required": ["drafts", "mechanism", "ignores"]}},
        "recombination": {"type": "object", "properties": {
            "elements": {"type": "array", "items": {"type": "object", "properties": {
                "draft": {"type": "integer"}, "element": {"type": "string"}}, "required": ["draft", "element"]}},
            "combined_mechanism": {"type": "string"},
            "workable": {"type": "boolean"},
            "beats_best_single_on_novelty": {"type": "boolean"},
            "reasoning": {"type": "string"}},
            "required": ["elements", "combined_mechanism", "workable", "beats_best_single_on_novelty", "reasoning"]},
        "best_single": {"type": "object", "properties": {
            "draft": {"type": "integer"}, "mechanism": {"type": "string"}, "why_furthest": {"type": "string"}},
            "required": ["draft", "mechanism", "why_furthest"]},
        "decision": {"type": "string", "enum": ["combination", "single"]},
        "pick": {"type": "object", "properties": {
            "mechanism": {"type": "string"}, "ignores": {"type": "string"}, "why_survived": {"type": "string"},
            "parentage": {"type": "array", "items": {"type": "object", "properties": {
                "draft": {"type": "integer"}, "contributed": {"type": "string"}}, "required": ["draft", "contributed"]}}},
            "required": ["mechanism", "ignores", "why_survived", "parentage"]},
        "final_draft": {"type": "string"},
    },
    "required": ["attractor", "set_aside", "clusters", "recombination", "best_single", "decision", "pick",
                 "final_draft"],
}

_sweep_lock = threading.Lock()


# --- the ladder and the sweep -----------------------------------------------------------------------------------


def sweep_enabled() -> bool:
    return os.environ.get("HANGGLIDER_SWEEP", "").strip().lower() in ("1", "true", "yes", "on")


def ladder_for_run(records_dir: Path = None) -> tuple[list[float], dict | None]:
    """The ladder for this run. Normal operation: the fixed LADDER. Sweep: the top rung steps through SWEEP_TOPS,
    one step per run, cycling; the step counter is kept in the records directory so it survives restarts."""
    if not sweep_enabled():
        return list(LADDER), None
    records_dir = records_dir or records_root()
    with _sweep_lock:
        records_dir.mkdir(parents=True, exist_ok=True)
        state = records_dir / ".sweep-state.json"
        step = json.loads(state.read_text()).get("next_step", 0) if state.exists() else 0
        state.write_text(json.dumps({"next_step": step + 1}))
    top = SWEEP_TOPS[step % len(SWEEP_TOPS)]
    return LADDER[:-1] + [top], {"step": step, "top_temperature": top}


# --- the panel ---------------------------------------------------------------------------------------------------


def angle_for(i: int) -> dict:
    return ANGLE_BANK[i % len(ANGLE_BANK)]


def taken_block(directions: list[str]) -> str:
    if not directions:
        return ""
    return TAKEN_BLOCK.format(lines="\n".join(f"- {d}" for d in directions))


def split_direction(text: str) -> tuple[str, str]:
    """(body, direction). The direction is the draft's own last 'Direction:' line; if the draft omitted it (high
    temperatures sometimes do), fall back to its first sentence, clipped, so the taken-list still grows."""
    m = None
    for m in re.finditer(r"(?im)^\W*direction\W*:\s*(.+)$", text):
        pass
    if m:
        return text[:m.start()].strip(), m.group(1).strip().strip("*_ ")[:200]
    flat = " ".join(text.split())
    first = re.split(r"(?<=[.!?])\s", flat, maxsplit=1)[0] if flat else "(empty draft)"
    return text.strip(), "(no Direction line; first sentence) " + first[:160]


def draft_messages(request: str, i: int, taken: list[str]) -> list[dict]:
    return [{"role": "user", "content": DRAFT_PROMPT.format(angle=angle_for(i)["brief"], request=request,
                                                            taken=taken_block(taken))}]


def run_panel(request: str, ladder: list[float], chat=None, on_draft=None) -> list[dict]:
    """Five drafts, sequential, bare model, think off. Draft i gets ladder[i], angle i and the taken-list so far."""
    chat = chat or ollama.chat
    drafts, taken = [], []
    for i, t in enumerate(ladder):
        msgs = draft_messages(request, i, taken)
        r = chat(msgs, think=False, options={"temperature": t, "num_ctx": 16384, "num_predict": DRAFT_TOKENS})
        body, direction = split_direction(r.content)
        drafts.append({"index": i + 1, "temperature": t, "angle": angle_for(i)["seat"],
                       "angle_brief": angle_for(i)["brief"], "taken_list": list(taken), "brief": msgs[0]["content"],
                       "text": r.content, "direction": direction, "eval_count": r.eval_count,
                       "done_reason": r.done_reason, "seconds": round(r.seconds, 2)})
        taken.append(direction)
        if on_draft:
            on_draft(i + 1, len(ladder))
    return drafts


# --- band representatives (medoid, never "best") --------------------------------------------------------------


def _bag(text: str) -> Counter:
    return Counter(re.findall(r"[a-z0-9']+", text.lower()))


def similarity(a: str, b: str) -> float:
    """Cosine similarity of word counts: crude, deterministic, and blind to quality."""
    x, y = _bag(a), _bag(b)
    dot = sum(x[w] * y[w] for w in x)
    na, nb = math.sqrt(sum(v * v for v in x.values())), math.sqrt(sum(v * v for v in y.values()))
    return dot / (na * nb) if na and nb else 0.0


def band_representatives(drafts: list[dict]) -> dict:
    """For each band, the medoid: the draft most similar to the band's other drafts. A two-draft band is symmetric
    (each is equally similar to the other), so ties break on mean similarity to the whole panel (the more typical
    draft), then on lower ladder position. No quality signal is used: the reassessor does not curate this."""
    texts = [d["text"] for d in drafts]
    n = len(texts)
    sim = [[similarity(texts[i], texts[j]) for j in range(n)] for i in range(n)]
    panel_mean = [sum(sim[i][j] for j in range(n) if j != i) / max(n - 1, 1) for i in range(n)]
    reps = {}
    for band, idx in BANDS.items():
        idx = [i for i in idx if i < n]
        if not idx:
            continue
        scored = []
        for i in idx:
            others = [j for j in idx if j != i]
            band_mean = sum(sim[i][j] for j in others) / len(others) if others else 1.0
            scored.append((round(band_mean, 9), round(panel_mean[i], 9), -i, i))
        best = max(scored)
        reps[band] = {"draft": best[3] + 1, "temperature": drafts[best[3]]["temperature"],
                      "band_similarity": best[0], "panel_similarity": best[1],
                      "tie_broken_by_panel": len(idx) > 1 and len({s[0] for s in scored}) == 1}
    return reps


# --- the reassessment ---------------------------------------------------------------------------------------------


def reassess(request: str, drafts: list[dict], chat=None) -> tuple[str, dict | None, str | None]:
    """One low-temperature call over the five drafts. Returns (raw verbatim output, parsed or None, parse error)."""
    chat = chat or ollama.chat
    shown = "\n\n".join(f"### Draft {d['index']} (angle: {d['angle']}, temperature {d['temperature']})\n{d['text']}"
                        for d in drafts)
    msgs = [{"role": "user", "content": REASSESS_PROMPT.format(request=request, drafts=shown)}]
    r = chat(msgs, think=False, format=REASSESS_SCHEMA,
             options={"temperature": REASSESS_TEMPERATURE, "num_ctx": 16384, "num_predict": REASSESS_TOKENS})
    try:
        parsed = json.loads(r.content)
        if not str(parsed.get("final_draft", "")).strip():
            return r.content, parsed, "empty final_draft"
        return r.content, parsed, None
    except Exception as e:
        return r.content, None, f"{type(e).__name__}: {e}"


# --- the card -----------------------------------------------------------------------------------------------------


def defang(text: str) -> tuple[str, list[str]]:
    """Hard boundary: no stamp string may leave this mode. If model text happens to contain one, it is replaced
    visibly (and the replacement is recorded), never passed through."""
    hits = []
    for s in FORBIDDEN_STAMPS:
        pattern = re.compile(re.escape(s), re.IGNORECASE)
        if pattern.search(text):
            hits.append(s)
            text = pattern.sub("[stamp string removed]", text)
    return text, hits


def _details(band: str, d: dict) -> str:
    body = d["text"].strip() or "(empty draft)"
    return (f"<details>\n<summary>{band} pass · temperature {d['temperature']} · {d['angle']}</summary>\n\n"
            f"{body}\n\n</details>")


def compose_card(final_draft: str, drafts: list[dict], reps: dict) -> str:
    """(1) the final draft labelled "hang glider"; (2-4) three collapsed raw passes; (5) nothing further.
    The '---' rule lets service.strip_reply keep only the final draft when the card is reused as chat history."""
    parts = [f"**{LABEL}**\n\n{final_draft.strip()}", "---"]
    parts += [_details(band, drafts[reps[band]["draft"] - 1]) for band in BANDS if band in reps]
    return "\n\n".join(parts) + "\n"


# --- the record ---------------------------------------------------------------------------------------------------


def write_record(record: dict, records_dir: Path = None) -> Path:
    records_dir = records_dir or records_root()
    records_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S-%f")
    path = records_dir / f"{stamp}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return path


# --- one run ------------------------------------------------------------------------------------------------------


def run(request: str, say=lambda m: None, chat=None, records_dir: Path = None) -> tuple[str, dict, Path]:
    """The whole mode: panel, reassessment, card, record. Returns (card, record, record path)."""
    started = time.time()
    ladder, sweep = ladder_for_run(records_dir)
    drafts = run_panel(request, ladder, chat, on_draft=lambda i, n: say(f"Panel draft {i}/{n} written"))
    say("Reassessing the spread")
    raw, parsed, error = reassess(request, drafts, chat)
    if parsed is not None and not error:
        final = parsed["final_draft"]
    else:  # no developed pick: present the draft furthest from the panel (lowest mean similarity), labelled raw
        far = min(range(len(drafts)), key=lambda i: sum(similarity(drafts[i]["text"], d["text"]) for d in drafts))
        final = drafts[far]["text"] + f"\n\n*(reassessment unavailable: raw draft {far + 1} shown, undeveloped)*"
    reps = band_representatives(drafts)
    card, removed = defang(compose_card(final, drafts, reps))
    record = {
        "mode": "hangglider", "request": request, "started": started, "finished": time.time(),
        "model": ollama.MODEL, "ladder": ladder, "sweep": sweep,
        "drafts": drafts,  # each: full text, temperature, angle, the taken-list as it stood, the full brief
        "taken_lists": [d["taken_list"] for d in drafts],
        "reassessment": {"temperature": REASSESS_TEMPERATURE, "raw": raw, "parsed": parsed, "error": error,
                         "label": "triage for novelty; not a judgment of truth"},
        "attractor": (parsed or {}).get("attractor"), "set_aside": (parsed or {}).get("set_aside"),
        "clusters": (parsed or {}).get("clusters"), "decision": (parsed or {}).get("decision"),
        "pick": (parsed or {}).get("pick"), "final_draft": final,
        "band_representatives": reps, "stamp_strings_removed": removed, "card": card,
    }
    path = write_record(record, records_dir)
    return card, record, path
