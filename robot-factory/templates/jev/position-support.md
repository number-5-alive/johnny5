# Jev template: position-support

PURPOSE: Ask Jev how well the state supports a position a seat has taken, and (only when an agreed record exists) whether the position contradicts that record.
CALLER: the moderator during a multi-seat session, for one seat's position at a time.
SLOTS: position, evidence
OPTIONAL: record
THRESHOLDS: Q1 normalized position (score / (n-1)) below 0.50 = weakly supported; flag it. Q2 (present only when {record} was given): Noul probability at or above 0.50 = the position contradicts the agreed record; stop and reconcile before continuing.

## State-assembly rules

1. One position per task, stated as a single claim.
2. Evidence trimmed to what is relevant: only the facts that bear on {position}. {record} is only the agreed lines the position might touch.
3. No counting questions.
4. No date arithmetic: precompute any intervals.
5. No indirect phrasing: state the position directly ("we should ship X first"), not as a report of what someone said.
6. {position} is one line with no "|". Omit --slot record entirely when there is no agreed record; the contradiction question is then dropped.

## Reading guide

- Q1 (Score, 5 levels): normalized position 0..1 (score / (n-1)) of evidential support.
- Q2 (Noul, only with a record): probability the position contradicts the record.
- Jev never grants the verified stamp.

## Block

```jev
JEV-STATE:
Position under audit: {position}

Evidence:
{evidence}
[if record]
[if record]Agreed record (settled earlier in this session):
[if record]{record}

JEV-QUESTIONS:
- Score: Evidential support for this position given the state: {position} | none | weak | moderate | strong | decisive
[if record]- Noul: This position contradicts the agreed record in the state: {position}
```
