"""Does a passage contain a SimpleQA gold answer? Used only for the retrieval-only check (stage 2.1)."""

import re

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]


def norm(s: str) -> str:
    s = s.lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)  # 120,000 -> 120000
    s = re.sub(r"[^\w\s.-]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def variants(gold: str) -> list[str]:
    g = norm(gold)
    out = {g}
    m = re.fullmatch(rf"({'|'.join(MONTHS)}) (\d{{1,2}}) (\d{{4}})", g) or None
    if m:  # "may 29 2023" -> "29 may 2023"
        out.add(f"{m[2]} {m[1]} {m[3]}")
    m = re.fullmatch(rf"(\d{{1,2}}) ({'|'.join(MONTHS)}) (\d{{4}})", g)
    if m:
        out.add(f"{m[2]} {m[1]} {m[3]}")
    return sorted(out)


def matchable(gold: str) -> bool:
    """Too-short golds ("3", "2") match almost any passage, so they are excluded from the metric."""
    g = norm(gold)
    return len(g) >= 3 and not (g.isdigit() and len(g) < 4)


def contains(gold: str, text: str) -> bool:
    t = f" {norm(text)} "
    return any(re.search(rf"(?<![\w]){re.escape(v)}(?![\w])", t) for v in variants(gold))
