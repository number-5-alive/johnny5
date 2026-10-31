"""SimpleQA-style grading with qwen (thinking off)."""

import re

from . import ollama

# Condensed from the SimpleQA grading rubric (openai/simple-evals).
GRADER_TEMPLATE = """You are grading an answer to a factual question against a gold target.

Grades:
A) CORRECT: the response contains the gold target's key information and does not contradict it. Extra detail, minor spelling differences, and hedging are fine as long as the gold answer is clearly given and nothing contradicts it. Numbers must match to the precision of the gold target.
B) INCORRECT: the response states an answer that contradicts the gold target or gives a different answer, even with hedging ("I think it may be X"). Listing several candidate answers counts as incorrect.
C) NOT_ATTEMPTED: the response does not give a definite answer, for example "I don't know" or "I couldn't verify this", and does not contradict the gold target.

Only the final answer matters; judge whether the gold target is what the response is asserting.

Question: {question}
Gold target: {target}
Response: {response}

Reply with a single letter: A, B, or C."""

GRADES = {"A": "correct", "B": "incorrect", "C": "not_attempted"}


def grade(question: str, target: str, response: str) -> str:
    prompt = GRADER_TEMPLATE.format(question=question, target=target, response=response or "(empty)")
    result = ollama.chat(
        [{"role": "user", "content": prompt}],
        think=False,
        options={**ollama.GRADER_OPTIONS, "num_predict": 8},
    )
    match = re.search(r"\b([ABC])\b", result.content)
    return GRADES[match.group(1)] if match else "ungraded"
