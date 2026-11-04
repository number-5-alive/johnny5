# The seat of consciousness

Above the two halves of this system, the home interpreter and
the universal interpreter, sits one more piece: a small,
deliberately strange composite whose only job is deciding what
a prompt needs. Its designer calls it the seat of consciousness:
the key he had been trying to build inside Johnny all along.

The idea is that a prompt reaches both interpreters at once,
the way a stimulus reaches a mind from inside and outside
together. A process above them decides which structures,
internal and external, need activation, and dispatches the work
already configured: not a destination picked from a list, but a
worker assembled per signal. A mind, a mode, a bundle of
shelves, a bundle of context.

## The mechanism

1. **Bids.** Both interpreters read the prompt and file an ask:
   what they would bring, what they would need. The knowledge of
   what each half holds stays in that half; neither bid is
   allowed to assert the other's facts.
2. **Translation.** A fast, small local model, fluent in one
   narrow command grammar rather than in the world, normalizes
   the prompt and the bids into a single dispatch command:
   allocations of worker, mode, shelves, context, and task. A
   validator checks the command against the real shelf registry,
   and a repair pass fixes what it flags.
3. **Division.** The command goes to Jev, the certainty
   instrument, which scores the possible divisions as
   probabilities. Jev decides nothing and stamps nothing; it
   prices the choice.
4. **Execution.** The switchboard executes the best-supported
   division, splitting to both halves when the probabilities run
   close, and the halves do the work under the usual rules: the
   shelves settle facts, the ledger records the dispatch, and
   the house's caps and vetoes still govern what may run.

The recipe is a composite on purpose: a language model to hear
the signal, a reasoning model to think about where it belongs,
a probability instrument to price the dispatch, and a
retrieval discipline to cross-check the choice against what the
shelves actually hold. Fast, because every part is small. Not
stupid, because the parts check each other.

## Status

Designed 2026-11-04 and probed live the same day: one real
prompt run through the full circuit, bids, translation, Jev
division, execution, with the record published below as a
labelled probe. It is not a production component. The probe is
evidence the shape works at first assembly, nothing more, and
it is written up that way.

- [`PROBE-2026-11-04.md`](PROBE-2026-11-04.md): the probe,
  including what went wrong in it
- [`artifacts/`](artifacts/): the bids, the translator's
  commands, Jev's reply, and the shelf's route, as they ran
