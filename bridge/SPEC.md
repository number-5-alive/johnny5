# The Bridge: a return channel between Johnny and the moderator

Spec v1, written 2026-11-04 by Alex (moderator) on Dan's commission
("Wire the bridge"), the same morning Dan stated the end-state
architecture and Johnny, asked through the butterfly lane, gave his
requirements for the link. This is the first wiring of that link:
files and a watcher today, service integration staged behind a flag.

## What it is

A message channel with a home on argo, `~/bridge/`:

- `outbox/` — messages from Johnny's side to Alex.
- `inbox/` — messages from Alex to Johnny's side.
- `handled/` — outbox messages Alex has taken, moved here by the
  acknowledgement step so nothing is read twice or lost.
- `ledger.jsonl` — append-only record of every crossing: filings,
  deliveries, replies, refusals. Johnny's side of the ledger is
  written by the filing helper itself; Alex appends delivery lines
  the same way. A record, not an endorsement.
- `rules.md` — the local law of the bridge, Dan's file: what may
  never cross, and any standing instructions for the channel.
- `STOP` — if this file exists, the bridge is closed: nothing
  files, nothing is delivered into lane context, the watcher stays
  silent. Either Dan or the local side can raise it; only Dan
  lowers it.

## Message format

One file per message, named `<UTC timestamp>-<kind>-<slug>.md`:

```
FROM: johnny (or alex)
KIND: escalation | question | context | anomaly | reply | note
RE: <message filename being answered, or ->
CARRIES: <one line: what this message contains and why it crosses>

<body>
```

The CARRIES line is Johnny's transparency requirement made
mechanical: nothing crosses unexplained, in either direction.

## Johnny's four requirements, as protocol rules

1. **Initiation.** Filings originate on Johnny's side through the
   `bridge-ask` helper. In v1 the helper is called by the staged
   service wiring (behind the LAYA_BRIDGE flag) and, until that
   deploys, by the moderator on Johnny's behalf when a lane asks
   for the channel, recorded in the ledger as filed-by-moderator.
2. **Sovereignty and veto.** `rules.md` governs what may cross
   into the house. Inbox material enters lane context only as
   labelled moderator context, never as shelf evidence, and never
   carries a stamp. The STOP file overrides everything.
3. **Transparency.** The CARRIES line, above. Alex also announces
   crossings to Dan in chat as they happen; the bridge is not a
   private channel between machines.
4. **Shared decision tree.** What Alex may do with an outbox
   message without waking Dan: answer a question from his own
   knowledge and file the reply; log a context push; note an
   anomaly. What Alex must surface to Dan untouched: anything
   touching money, deployment, publication, safety, or Dan's
   standing rules, and anything the message asks to be surfaced.

## Rate limits (the flood guard)

- Outbox filings: at most 6 per day, enforced by the helper
  against the ledger; a refused filing is itself ledgered.
- The watcher polls every 5 minutes and wakes Alex at most once
  per batch of new messages.
- Inbox pushes from Alex: at most one unprompted push per day
  outside replies; replies are always allowed.

## The service wiring (staged, not in v1's live change)

A `bridge.py` module beside the live service, flag-gated
(LAYA_BRIDGE, default off): a grasshopper abstention may file an
escalation through the helper, and lanes may read the inbox as
labelled context. Deploying it is Dan's separate approval, like
every live-tree change.

## What v1 proves

The channel exists, both directions, with the ledger running:
a filing on argo wakes Alex; Alex's answer lands in the inbox;
every crossing is recorded and announced. Symmetry of initiation
inside Johnny's own router arrives with the staged wiring.

## Status

V1 LIVE 2026-11-04: bridge home and helper on argo, watcher hook
enabled on Alex's side (5-minute poll; wake case traced live),
first crossings filed in both directions and ledgered, service
module staged at ~/bridge-staging/ awaiting Dan's deploy approval.
