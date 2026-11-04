"""The bridge: Johnny's side of the return channel to the moderator.

Staged module for the laya-qwen service (bridge-spec.md, 2026-11-04).
Flag-gated by LAYA_BRIDGE (default off): with the flag unset or not
"on", every public function here is inert and the lanes never see
this module.

What it does when enabled:
- file_escalation(): file a message into ~/bridge/outbox through
  the bridge-ask helper (which enforces the STOP file and the
  daily rate limit, and writes the ledger line). Never raises into
  a lane path: a refused or failed filing returns None.
- read_inbox(): read moderator messages from ~/bridge/inbox.
- inbox_context(): format inbox messages as a labelled context
  block. Inbox material is context, never evidence, and carries
  no stamp; the label says so every time.

Nothing here grants the bridge any authority: filings are
messages, not commands, and the moderator's side applies its own
decision tree (bridge-spec.md) to everything that crosses.
"""

import os
import subprocess

_HELPER = os.path.expanduser("~/bridge/bridge-ask")
_INBOX = os.path.expanduser("~/bridge/inbox")


def enabled() -> bool:
    return os.environ.get("LAYA_BRIDGE", "off").strip().lower() == "on"


def file_escalation(kind: str, carries: str, body: str, slug: str = "msg",
                    filed_by: str = "johnny") -> str | None:
    """File one outbox message via the helper. Returns the filename
    or None (flag off, STOP present, rate limited, helper failed)."""
    if not enabled():
        return None
    try:
        proc = subprocess.run(
            [_HELPER, "file", "--from", filed_by, "--kind", kind,
             "--carries", carries, "--slug", slug],
            input=body, capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def read_inbox(limit: int = 5) -> list[dict]:
    """Read up to `limit` inbox messages, oldest first."""
    out: list[dict] = []
    if not os.path.isdir(_INBOX):
        return out
    for name in sorted(os.listdir(_INBOX)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(_INBOX, name)
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        head, _, body = text.partition("\n\n")
        msg = {"file": name, "body": body.strip()}
        for line in head.splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                msg[k.strip().lower()] = v.strip()
        out.append(msg)
        if len(out) >= limit:
            break
    return out


def inbox_context(limit: int = 5) -> str:
    """The labelled context block for lane prompts, or "" if the
    flag is off or the inbox is empty."""
    if not enabled():
        return ""
    msgs = read_inbox(limit)
    if not msgs:
        return ""
    lines = ["[Moderator context via the bridge: context only, not "
             "evidence, carries no stamp.]"]
    for m in msgs:
        lines.append(f"- ({m.get('kind', 'note')}) {m.get('carries', '')}")
        if m["body"]:
            lines.append(f"  {m['body']}")
    return "\n".join(lines)
