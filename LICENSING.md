# Licensing: which parts of Johnny 5 carry which license

Draft prepared 2026-11-04, applying the position of SAINT decision
record 036s1, ratified by the maintainer the same day. This note takes
effect with the first release published under it. The November 2026
release is licensed under the Apache License 2.0 in full, and nothing
in this note changes that release.

## The split

Johnny 5 uses two licenses:

- The **core** is licensed under the GNU Affero General Public
  License v3.0 (AGPLv3), the text in `LICENSE` from the release that
  adopts this note onward.
- **Genuinely separable libraries** are licensed under the Apache
  License 2.0, the text in `LICENSE-APACHE`, and are listed by name
  below.

Which license governs a piece of code depends on what the code is and
how it combines with the rest, not on labels or file placement alone.

## What is core

Everything in this project is core unless it is listed as a library
below. Core includes:

- the router
- the answering lanes (verified, fast, bare, and novelty)
- the specialist shelves and their retrieval and grading machinery
- the cross-checking and agreement logic, including the verified
  stamp
- the Robot Factory and S.A.I.N.T. machinery: the session runner,
  the budget and ledger, the scribe, the rulesets, and the seat
  adapters
- provider adapters and schemas that are coupled to core behavior

## What may be a library

A piece may be licensed as a library only if it can stand apart and
be embedded in another project without forming a combined work with
the core. Candidates, as they are extracted and published on their
own:

- client SDKs for talking to a running Johnny 5
- data schemas and message formats, as standalone definitions
- small standalone utilities

Provider adapters and tightly coupled schemas stay core unless a
change to this note documents a clear, maintainable boundary for
them. When in doubt, a piece is core.

## Library list

As of adoption, no part of the current tree is separately licensed:
the whole project is core. Pieces will be added to this list by name,
with their paths, as they are extracted.

## Commercial terms

The maintainer may in future offer separate commercial terms for the
core. None are offered now, and nothing here is an offer. Whether any
piece of code can be covered by such terms depends on the rights the
project holds in it and on the licenses of its dependencies, which
are tracked in the project's dependency license inventory.

## Trademarks

No license in this project grants any right to the Johnny 5 or
Number 5 Alive names or marks.
