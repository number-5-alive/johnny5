# Jev template: claim-support

PURPOSE: Ask Jev whether a stated answer is supported by the evidence given, and how confident it is that the answer is correct on that evidence alone.
CALLER: the moderator (or a verifier seat's round) after a seat has produced an answer with cited evidence.
SLOTS: question, answer, evidence
OPTIONAL:
THRESHOLDS: Tripwire if the Noul probability (Q1) is below 0.50: the answer is NOT supported by the evidence; send it back. Q2 is advisory: a normalized position (score / (n-1)) below 0.50 means "probably wrong given only this evidence".

## State-assembly rules

1. One claim only. {answer} must be a single assertion; split a compound answer into separate claim-support tasks.
2. Evidence trimmed to what is relevant: paste only the passages that bear on {answer}, with no surrounding chatter, transcripts or boilerplate.
3. No counting questions: do not ask Jev how many of something there are; state counts in the evidence and ask about a claim instead.
4. No date arithmetic: compute any intervals, ages or deadlines yourself and put the computed figure in the evidence.
5. No indirect phrasing: write the answer as a direct, positive statement ("X is Y"), not "it is not the case that X is not Y" and not "the seat claimed that...".
6. Slots used in a question line ({answer}) must be one line with no "|".

## Reading guide

- Q1 (Noul "the evidence fully supports the answer"): the probability the claim holds. Below 0.50 = tripwire.
- Q2 (Score, 5 levels): the score on the 0..n-1 scale (e.g. "3.95 of 4"), the nearest level and the normalized position 0..1 = score / (n-1), lowest level = 0. Read it as Jev's graded confidence, never as proof.
- Jev never grants the verified stamp; it only flags doubt.

## Block

```jev
JEV-STATE:
Question: {question}

Answer under audit: {answer}

Evidence (the only material to judge by):
{evidence}

JEV-QUESTIONS:
- Noul: The evidence fully supports this answer: {answer}
- Score: Confidence that the answer is correct given only this evidence | very low | low | moderate | high | very high
```
