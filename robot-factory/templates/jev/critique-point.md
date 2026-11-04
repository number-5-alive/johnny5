# Jev template: critique-point

PURPOSE: Ask Jev whether ONE point raised by a critic identifies a real defect in the artifact under review.
CALLER: the moderator, once per critique point, when deciding which review points to act on.
SLOTS: artifact, point
OPTIONAL:
THRESHOLDS: Act on the point if the normalized position of Q1 is at least 0.60. Normalized position = score / (n-1): Jev's score is a number on the continuous scale 0 (lowest level) .. n-1 (highest level), e.g. 3.95 of 4 (live, task 019), so with 5 levels the position is score / 4. With the 5 levels below that is 0 for "certainly not a defect" up to 1 for "certainly a real defect"; 0.60 sits just past the middle level ("uncertain" = 0.50).

## State-assembly rules

1. One point per task. If a critic raised several points, render one critique-point task per point.
2. Evidence trimmed to what is relevant: {artifact} is only the excerpt the point is about (the function, the paragraph), not the whole file.
3. No counting questions ("how many bugs are there?"); the point names one defect.
4. No date arithmetic: if the point depends on dates or durations, state the computed result in the artifact excerpt.
5. No indirect phrasing: state the point as a direct claim of a defect ("the loop skips the last item"), not "it might be argued that...".
6. {point} is one line with no "|".

## Reading guide

- Q1 (Score, 5 levels, lowest first): the score ("3.95 of 4 — between ... and ..., near ..."), the nearest level and the normalized position score / (n-1). Position >= 0.60 (score >= 2.4 of 4) = act on the point; below = park it.
- The normalized position comes from the score itself and is always present. If Jev also returns probabilities the adapter adds a probability-weighted position (sum p_i * i / (n-1)) as a cross-check only; the threshold reads the normalized position.
- Jev never grants the verified stamp; "not a defect" is not a pass.

## Block

```jev
JEV-STATE:
Artifact excerpt under review:
{artifact}

Critique point: {point}

JEV-QUESTIONS:
- Score: This point identifies a real defect in the artifact: {point} | certainly not a defect | probably not a defect | uncertain | probably a real defect | certainly a real defect
```
