"""End-to-end checks against a running service. Usage: uv run python scripts/service_smoke.py http://127.0.0.1:8199"""

import json
import sys
import threading
import time

import httpx

BASE = sys.argv[1].rstrip("/")


def stream(model: str, messages: list[dict], label: str, out: dict, stop_after: float | None = None) -> None:
    t, text = time.monotonic(), ""
    with httpx.stream("POST", f"{BASE}/v1/chat/completions", timeout=900,
                      json={"model": model, "messages": messages, "stream": True}) as r:
        for line in r.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            delta = json.loads(line[6:])["choices"][0]["delta"]
            text += delta.get("content", "") or ""
            if stop_after and time.monotonic() - t > stop_after:
                out[label] = (round(time.monotonic() - t, 1), text + "\n[client disconnected]")
                return
    out[label] = (round(time.monotonic() - t, 1), text)


def show(label: str, res) -> None:
    secs, text = res
    print(f"\n{'=' * 30} {label} ({secs}s)\n{text}")


out: dict = {}
q1 = "Who received the IEEE Frank Rosenblatt Award in 2010?"

# 1. Background-task model: non-streaming, no progress block.
t = time.monotonic()
r = httpx.post(f"{BASE}/v1/chat/completions", timeout=120, json={"model": "qwen-quick", "messages": [
    {"role": "user", "content": "Generate a concise 3-5 word title for a chat about: " + q1}]}).json()
show("qwen-quick (non-stream)", (round(time.monotonic() - t, 1), r["choices"][0]["message"]["content"]))

# 2. Verified, factual.
stream("laya-qwen-verified", [{"role": "user", "content": q1}], "verified", out)
show("verified", out["verified"])

# 3. Follow-up: needs the rewrite.
stream("laya-qwen-fast", [{"role": "user", "content": q1}, {"role": "assistant", "content": out["verified"][1]},
                          {"role": "user", "content": "What country is he from?"}], "fast follow-up", out)
show("fast follow-up", out["fast follow-up"])

# 4. Not a lookup question: routed to plain qwen.
stream("laya-qwen-verified", [{"role": "user", "content": "Write a haiku about rain on a tin roof."}], "routing", out)
show("routing (non-factual)", out["routing"])

# 5. Two requests at once: the second must queue, and its time limit starts when it runs.
a = threading.Thread(target=stream, args=("laya-qwen-fast", [{"role": "user", "content": "What year was the Cure ADOA Foundation founded?"}], "concurrent A", out))
b = threading.Thread(target=stream, args=("laya-qwen-fast", [{"role": "user", "content": "In what city was the 6th ASEM Education Ministers' Meeting held?"}], "concurrent B", out))
a.start(); time.sleep(1); b.start(); a.join(); b.join()
show("concurrent A", out["concurrent A"]); show("concurrent B", out["concurrent B"])

# 6. Client disconnects mid-run; the next request must wait for the abandoned run to finish.
d = threading.Thread(target=stream, args=("laya-qwen-verified", [{"role": "user", "content": "Who played the vampire in Penny Dreadful's Season 1?"}], "disconnect", out), kwargs={"stop_after": 15})
d.start(); d.join()
print("\nhealth right after disconnect:", httpx.get(f"{BASE}/health").json())
stream("laya-qwen-fast", [{"role": "user", "content": "How many CDs did the original Seiken Densetsu 3 soundtrack include?"}], "after disconnect", out)
show("disconnect", out["disconnect"]); show("after disconnect", out["after disconnect"])
