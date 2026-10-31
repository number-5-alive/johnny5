"""Phoenix tracing for the answering service: OpenTelemetry + OpenInference attributes, exported over OTLP gRPC.

Fail-open by construction:
  - spans are exported by OpenTelemetry's BatchSpanProcessor on its own thread; a request never waits on Phoenix;
  - every call into OpenTelemetry from here is wrapped, so a tracing error can't reach the answering code;
  - exporter failures are logged once per target (host:port), not per request or per batch.

Config (read per request from service.json, like show_guesses):
  "phoenix": {"enabled": true, "endpoint": "http://localhost:4317"}
Disabling turns span creation off immediately; changing the endpoint swaps the exporter on the next request.
"""

import json
import logging
import re
import threading
import time
from contextlib import contextmanager

log = logging.getLogger("laya_qwen.tracing")

DEFAULTS = {"enabled": True, "endpoint": "http://localhost:4317"}
PROJECT = "laya-qwen"
MAX_TEXT = 4000  # characters kept per input/output attribute

_lock = threading.Lock()
_state = {"endpoint": None, "provider": None, "tracer": None, "broken": False}


class _OnceFilter(logging.Filter):
    """Let the first exporter error per target (host:port) through, then stay quiet about that target."""

    def __init__(self):
        super().__init__()
        self.seen: set[str] = set()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.WARNING:
            return True
        m = re.search(r"traces to ([\w.\-\[\]:]+?:\d+)", record.getMessage())
        target = m.group(1) if m else "?"
        if target in self.seen:
            return False
        self.seen.add(target)
        record.msg = f"Phoenix export failing for {target} (further errors for it are suppressed): {record.getMessage()}"
        record.args = ()
        return True


_once = _OnceFilter()
for _name in ("opentelemetry.exporter.otlp.proto.grpc.exporter", "opentelemetry.sdk.trace.export",
              "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"):
    logging.getLogger(_name).addFilter(_once)


def config(service_cfg: dict) -> dict:
    return {**DEFAULTS, **(service_cfg.get("phoenix") or {})}


def _build(endpoint: str):
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from openinference.semconv.resource import ResourceAttributes

    provider = TracerProvider(resource=Resource.create({
        "service.name": "laya-qwen", ResourceAttributes.PROJECT_NAME: PROJECT}))
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True, timeout=3)
    provider.add_span_processor(BatchSpanProcessor(exporter, max_queue_size=2048, schedule_delay_millis=2000,
                                                   export_timeout_millis=5000))
    return provider, provider.get_tracer("laya_qwen.service")


def tracer(service_cfg: dict):
    """The tracer for the configured endpoint, or None if tracing is off or unavailable. Never raises."""
    try:
        cfg = config(service_cfg)
        if not cfg.get("enabled"):
            return None
        endpoint = cfg["endpoint"]
        with _lock:
            if _state["endpoint"] != endpoint:
                old = _state["provider"]
                _state.update(endpoint=endpoint, provider=None, tracer=None, broken=False)
                if old is not None:  # flush and close the old exporter off the request path
                    threading.Thread(target=old.shutdown, daemon=True).start()
                try:
                    _state["provider"], _state["tracer"] = _build(endpoint)
                except Exception as e:
                    _state["broken"] = True
                    log.warning("Phoenix tracing unavailable (%s: %s); answering continues without it",
                                type(e).__name__, e)
            return None if _state["broken"] else _state["tracer"]
    except Exception:
        return None


def _clip(v):
    if isinstance(v, str):
        return v[:MAX_TEXT]
    if isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, (list, tuple)) and all(isinstance(x, (str, int, float, bool)) for x in v):
        return [x[:MAX_TEXT] if isinstance(x, str) else x for x in v]
    return json.dumps(v, default=str)[:MAX_TEXT]


class Span:
    """A span handle whose methods never raise; a no-op when tracing is off."""

    def __init__(self, span=None):
        self._span = span

    def set(self, **attrs) -> "Span":
        if self._span is not None:
            for k, v in attrs.items():
                if v is None:
                    continue
                try:
                    self._span.set_attribute(k.replace("__", "."), _clip(v))
                except Exception:
                    pass
        return self

    def error(self, exc: BaseException) -> None:
        if self._span is not None:
            try:
                from opentelemetry.trace import Status, StatusCode

                self._span.record_exception(exc)
                self._span.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
            except Exception:
                pass


@contextmanager
def span(tr, name: str, kind: str = "CHAIN", **attrs):
    """Child span of the current one (or a root span). kind: OpenInference span kind (CHAIN, LLM, RETRIEVER)."""
    cm = None
    if tr is not None:
        try:
            cm = tr.start_as_current_span(name)
            s = Span(cm.__enter__())
            s.set(openinference__span__kind=kind, **attrs)
        except Exception:
            cm, s = None, Span()
    else:
        s = Span()
    try:
        yield s
    except BaseException as e:
        s.error(e)
        if cm is not None:
            try:
                cm.__exit__(type(e), e, e.__traceback__)
            except Exception:
                pass
            cm = None
        raise
    finally:
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                pass


def llm_attrs(model: str, messages: list[dict], result=None) -> dict:
    """OpenInference LLM attributes for one Ollama chat call."""
    a = {"llm__model_name": model, "llm__provider": "ollama",
         "input__value": messages[-1]["content"] if messages else ""}
    for i, m in enumerate(messages[-6:]):
        a[f"llm__input_messages__{i}__message__role"] = m["role"]
        a[f"llm__input_messages__{i}__message__content"] = m["content"]
    if result is not None:
        a.update({"output__value": result.content,
                  "llm__output_messages__0__message__role": "assistant",
                  "llm__output_messages__0__message__content": result.content,
                  "llm__token_count__prompt": result.prompt_eval_count,
                  "llm__token_count__completion": result.eval_count,
                  "llm__token_count__total": (result.prompt_eval_count or 0) + (result.eval_count or 0),
                  "laya__latency_seconds": round(result.seconds, 3), "laya__done_reason": result.done_reason,
                  "laya__thinking_chars": len(result.thinking or "")})
    return a


def past_llm_span(tr, name: str, start_ns: int, end_ns: int, attrs: dict) -> None:
    """Record an LLM call that has already finished (drafts are timed from the pipeline's progress callback)."""
    if tr is None:
        return
    try:
        s = tr.start_span(name, start_time=start_ns)
        Span(s).set(openinference__span__kind="LLM", **attrs)
        s.end(end_time=end_ns)
    except Exception:
        pass


def now_ns() -> int:
    return time.time_ns()
