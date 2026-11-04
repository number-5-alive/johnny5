# Jev template: draft-agreement

PURPOSE: Ask Jev whether two to five drafts (from different seats) agree in substance on one central claim.
CALLER: the moderator before merging seat drafts, to decide whether a merge is a summary or an arbitration.
SLOTS: claim, draft1, draft2
OPTIONAL: draft3, draft4, draft5
THRESHOLDS: Q1 Noul probability at or above 0.50 = the drafts agree on the central claim; below = arbitrate. Q2 normalized position (score / (n-1)) below 0.50 = agreement is weak even if Q1 passes; read the drafts.

## State-assembly rules

1. One central claim, named in {claim}; the drafts are judged only on it.
2. Evidence trimmed to what is relevant: each draft slot is the excerpt that addresses {claim}, not the whole draft. Up to five drafts.
3. No counting questions ("how many drafts agree?"); ask about agreement as a claim.
4. No date arithmetic.
5. No indirect phrasing: {claim} is a direct statement.
6. {claim} is one line with no "|".

## Reading guide

- Q1 (Noul): probability the drafts agree in substance on {claim}.
- Q2 (Score, 5 levels): normalized position 0..1 (score / (n-1)) of the strength of agreement.
- Jev never grants the verified stamp; agreement between drafts is not correctness.

## Block

```jev
JEV-STATE:
Central claim: {claim}

Draft 1:
{draft1}

Draft 2:
{draft2}
[if draft3]
[if draft3]Draft 3:
[if draft3]{draft3}
[if draft4]
[if draft4]Draft 4:
[if draft4]{draft4}
[if draft5]
[if draft5]Draft 5:
[if draft5]{draft5}

JEV-QUESTIONS:
- Noul: The drafts agree in substance on the central claim: {claim}
- Score: Strength of the drafts' substantive agreement on: {claim} | none | weak | partial | strong | complete
```
