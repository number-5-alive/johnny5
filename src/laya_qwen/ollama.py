"""Minimal Ollama chat client."""

import os
import time
from dataclasses import dataclass

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://argo:11434")
MODEL = os.environ.get("LAYA_QWEN_MODEL", "qwen3.6:27b")

# Qwen-recommended sampling for thinking mode.
THINKING_OPTIONS = {"temperature": 1.0, "top_p": 0.95, "top_k": 20}
GRADER_OPTIONS = {"temperature": 0.0}


@dataclass
class ChatResult:
    content: str
    thinking: str
    eval_count: int
    prompt_eval_count: int
    seconds: float
    done_reason: str


def chat(
    messages: list[dict],
    *,
    think: bool,
    options: dict | None = None,
    model: str = MODEL,
    timeout: float = 600.0,
    format: dict | str | None = None,
) -> ChatResult:
    payload = {
        "model": model,
        "messages": messages,
        "think": think,
        "stream": False,
        "options": options or {},
    }
    if format is not None:
        payload["format"] = format
    start = time.monotonic()
    resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    msg = data.get("message", {})
    return ChatResult(
        content=msg.get("content", "").strip(),
        thinking=msg.get("thinking", "") or "",
        eval_count=data.get("eval_count", 0),
        prompt_eval_count=data.get("prompt_eval_count", 0),
        seconds=time.monotonic() - start,
        done_reason=data.get("done_reason", ""),
    )
