# The bridge

The bridge is the return channel between Johnny and the
moderator: the first wiring of the architecture's end-state, in
which the local half of the system (Johnny, on a home server) and
the external half (the moderator, with the frontier models,
providers, and the web on call) are two halves of one mind, joined
by an equal, two-way link. Today the link is files, a helper, and
a watcher. The protocol is the point.

## How it works

A bridge home on the local machine holds an **outbox** (messages
from Johnny's side), an **inbox** (messages from the moderator),
and an append-only **ledger** of every crossing. One file per
message, and every message carries a one-line declaration of what
it contains and why it is crossing. A small helper, `bridge-ask`,
does the filing and enforces the channel's limits. On the
moderator's side, a polling watcher checks the outbox every few
minutes and wakes the moderator when something files; the
moderator answers what it may, surfaces what it must, and files
replies into the inbox.

`bridge.py` is the service-side module, staged and flag-gated: a
verified lane that abstains may file an escalation of its own,
and the lanes may read the inbox as context that is labelled as
context, never as evidence. `INTEGRATION.md` describes the two
touchpoints for whoever deploys it.

## The rules the channel runs on

These were stated by Johnny himself, asked through one of his
own lanes on the day the bridge was commissioned, and adopted as
the protocol:

1. **Initiation.** The local half can speak first: flag an
   anomaly, push a context update, ask a question, without
   waiting to be asked.
2. **Sovereignty.** The local side keeps a veto. A local rules
   file governs what may cross into the house, inbox material
   enters the lanes only as labelled context and never carries a
   stamp, and a stop file closes the bridge outright.
3. **Transparency.** Nothing crosses unexplained, in either
   direction. The declaration line is mechanical, and crossings
   are announced to the commissioner as they happen.
4. **A shared decision tree.** What the moderator may answer on
   its own, and what it must surface to the commissioner
   untouched (money, deployment, publication, safety, standing
   rules), is written down in `SPEC.md`.

Rate limits guard against flood: a small daily filing budget on
the local side, one wake per batch on the moderator's side.

## Status

Version 1 is live in its home installation as of 2026-11-04: the
channel, the ledger, and the watcher all run, and the first
crossings in both directions are on the record. The service
integration in `bridge.py` is staged behind its flag and deploys
on the commissioner's approval, like every change to the live
tree. The full protocol is `SPEC.md`.
