# Bridge integration notes (for the deploy step)

Staged 2026-11-04 with bridge.py. Deploying is Dan's separate
approval, like every live-tree change. Nothing here is live: the
module is inert without LAYA_BRIDGE=on, and service.py is not
touched by the staging at all.

At deploy time:

1. Copy `bridge.py` into `src/laya_qwen/`, beside `code_shelf.py`
   and `hangglider.py`.
2. Touchpoint 1, initiation: in the grasshopper path, at the
   existing abstention return, call
   `bridge.file_escalation("escalation", carries, body)` with a
   one-line carries summary and a body holding the question and
   what the lane tried. Fire-and-forget: the return value is
   ignored by the lane, and a filing failure changes nothing.
3. Touchpoint 2, inbox as context: in the butterfly and
   grasshopper prompt assembly, append `bridge.inbox_context()`
   when it returns non-empty. The block labels itself as
   moderator context, not evidence, no stamp.
4. Set `LAYA_BRIDGE=on` in the service environment only after the
   flag-off regression smoke passes (all lanes answer as before).
   Then smoke the flag-on path: ask grasshopper a question it
   must abstain on and watch `~/bridge/outbox/` for the filing
   and the ledger for its line.

Rollback: unset LAYA_BRIDGE and restart the service; the module
goes inert. Removing bridge.py entirely also restores the prior
tree, since no other file depends on it when the flag is off.
