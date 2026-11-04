"""Read-only status feed for the indicator board (task 032): GET /status (JSON) and GET /board (the page).

Lane state: `observed(run_job)` wraps the worker-thread job at the dispatch point. It only records the lane name and
start time on entry and clears them on exit; it never branches on, delays, or alters the request. Any failure inside
the observation itself is swallowed so the job runs exactly as it would unwrapped.

Session state: read from the factory's own files under RF_FACTORY_DIR (default ~/robot-factory), never written.
The rule (see work/032-status-board/REPORT.md):
  1. Session run: sessions/<id>/session.log whose first line is `OPEN session <id> ruleset=<r>`, with no `CLOSE` line,
     no sessions/<id>/session.json (written only at close) and no records/<id>-record.md (written only after close),
     and whose last activity is fresher than RF_SESSION_STALE_HOURS (default 3). Ruleset from the OPEN line.
  2. Otherwise, a task run: the newest `planned` ledger line whose call_id has no `actual` line, whose round has no
     records/<round>-record.md and no sessions/<round>/ dir, and which is fresher than RF_SESSION_STALE_HOURS. Ruleset "factory" (task runs go
     through run-next.sh, the Factory's runner; SAINT only ever runs through session.py, which writes session.log).
  Anything absent, unreadable, or not matching yields "session": null. Reading never raises into the response.
"""

import collections
import functools
import itertools
import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

BOARD_HTML = Path(os.environ.get("LAYA_STATUS_BOARD", Path(__file__).with_name("board.html"))).expanduser()
LEDGER_TAIL_BYTES = 256 * 1024
MAX_EVENTS = 8

_lock = threading.Lock()
_active: dict[int, tuple[str, str]] = {}  # token -> (lane, since); one runs at a time, but never assume it
_lane_events: collections.deque = collections.deque(maxlen=MAX_EVENTS)
_tokens = itertools.count()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --- lane observation (the only thing that touches the dispatch path) ------------------------------------------


def observed(job):
    """Wrap a worker job `job(model, ...)`: record (model, start) while it runs. Observation only."""

    @functools.wraps(job)
    def run(model, *args, **kwargs):
        token = None
        try:
            token, t = next(_tokens), _now()
            with _lock:
                _active[token] = (str(model), t)
                _lane_events.append({"t": t, "kind": "lane", "label": f"{model} started"})
        except Exception:
            pass
        try:
            return job(model, *args, **kwargs)
        finally:
            try:
                with _lock:
                    lane, _ = _active.pop(token)
                    _lane_events.append({"t": _now(), "kind": "lane", "label": f"{lane} finished"})
            except Exception:
                pass

    return run


def lane_state() -> dict:
    with _lock:
        if not _active:
            return {"active": None, "since": None}
        lane, since = _active[max(_active)]  # newest, should two ever overlap
        return {"active": lane, "since": since}


# --- factory session state (read-only) -------------------------------------------------------------------------


def _factory_dir() -> Path:
    return Path(os.environ.get("RF_FACTORY_DIR", "~/robot-factory")).expanduser()


def _stale_after() -> timedelta:
    try:
        return timedelta(hours=float(os.environ.get("RF_SESSION_STALE_HOURS", "3")))
    except ValueError:
        return timedelta(hours=3)


def _ts(s) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s))
        return d if d.tzinfo else None  # a timestamp without a zone is ambiguous
    except (TypeError, ValueError):
        return None


def _ledger_tail(base: Path) -> list[dict]:
    path = base / "ledger.jsonl"
    if not path.is_file():
        return []
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - LEDGER_TAIL_BYTES))
        raw = f.read().decode("utf-8", "replace")
    lines = raw.splitlines()
    if size > LEDGER_TAIL_BYTES:
        lines = lines[1:]  # first line is probably cut
    out = []
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and _ts(d.get("t")) and d.get("round"):
            out.append(d)
    return out


def _recorded(base: Path, name: str) -> bool:
    return (base / "records" / f"{name}-record.md").exists()


_OPEN = re.compile(r"^(\S+) OPEN session (\S+) ruleset=(\S+)")
_LINE = re.compile(r"^(\S+) (.*)$")


def _open_session_run(base: Path, now: datetime) -> dict | None:
    sessions = base / "sessions"
    if not sessions.is_dir():
        return None
    best = None
    for d in sessions.iterdir():
        log = d / "session.log"
        if not log.is_file() or (d / "session.json").exists() or _recorded(base, d.name):
            continue
        lines = [l for l in log.read_text(errors="replace").splitlines() if l.strip()]
        m = _OPEN.match(lines[0]) if lines else None
        if not m or m.group(2) != d.name or any(l.split(" ", 1)[-1].startswith("CLOSE") for l in lines):
            continue
        last = _LINE.match(lines[-1])
        last_t = _ts(last.group(1)) if last else None
        if not last_t or now - last_t > _stale_after():
            continue
        phase = last.group(2)
        phase = "opened" if phase.startswith("OPEN ") else re.split(r"[:;(]", phase, 1)[0][:48].strip()
        if best is None or last_t > best[0]:
            best = (last_t, {"ruleset": m.group(3), "name": d.name, "phase": phase})
    return best[1] if best else None


def _open_task_run(base: Path, rows: list[dict], now: datetime) -> dict | None:
    closed = {r.get("call_id") for r in rows if r.get("phase") == "actual"}
    for r in reversed(rows):
        if r.get("phase") != "planned" or not r.get("call_id") or r["call_id"] in closed:
            continue
        if now - _ts(r["t"]) > _stale_after():
            return None  # rows are in time order: everything older is staler still
        if _recorded(base, r["round"]) or (base / "sessions" / r["round"]).exists():
            continue  # recorded = finished; a sessions/ dir means rule 1 governs it (and it did not match)
        return {"ruleset": "factory", "name": r["round"], "phase": f"{r.get('seat', 'seat')} working"}
    return None


def session_state(rows: list[dict]) -> dict | None:
    try:
        base, now = _factory_dir(), datetime.now().astimezone()
        return _open_session_run(base, now) or _open_task_run(base, rows, now)
    except Exception:
        return None


def _session_events(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows[-MAX_EVENTS:]:
        label = f"{r['round']}: {r.get('phase', '?')}" + (f" ({r['seat']})" if r.get("seat") else "")
        out.append({"t": r["t"], "kind": "session", "label": label})
    return out


# --- routes ----------------------------------------------------------------------------------------------------


@router.get("/status")
def status():
    try:
        rows = _ledger_tail(_factory_dir())
    except Exception:
        rows = []
    with _lock:
        lane_events = list(_lane_events)
    events = lane_events + _session_events(rows)  # each source is in write order
    floor = datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
    order = sorted(range(len(events)), key=lambda i: (_ts(events[i]["t"]) or floor, i), reverse=True)
    events = [events[i] for i in order]  # newest first; same-second ties keep the later-written one first
    return JSONResponse({"generated_at": _now(), "lane": lane_state(), "session": session_state(rows),
                         "events": events[:MAX_EVENTS]}, headers={"Cache-Control": "no-store"})


@router.get("/board")
def board():
    try:
        return HTMLResponse(BOARD_HTML.read_text(), headers={"Cache-Control": "no-store"})
    except OSError:
        return JSONResponse({"error": f"board page not found at {BOARD_HTML}"}, 404)
