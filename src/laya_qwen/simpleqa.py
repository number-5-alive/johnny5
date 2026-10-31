"""SimpleQA loading and the fixed held-out split."""

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_CSV = ROOT / "data" / "raw" / "simple_qa_test_set.csv"
SPLIT_FILE = ROOT / "data" / "splits" / "heldout_200.json"
DATA_URL = "https://openaipublic.blob.core.windows.net/simple-evals/simple_qa_test_set.csv"

HELDOUT_SIZE = 200
SPLIT_SEED = 20261014


@dataclass
class Item:
    id: int  # row index in the official CSV
    question: str
    answer: str
    topic: str


def load_all() -> list[Item]:
    if not RAW_CSV.exists():
        raise SystemExit(f"Missing {RAW_CSV}. Download it with:\n  curl -sSL -o {RAW_CSV} {DATA_URL}")
    items = []
    with RAW_CSV.open(newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            topic = ""
            # metadata is a Python-literal dict; only the topic is needed.
            if "'topic': '" in row["metadata"]:
                topic = row["metadata"].split("'topic': '", 1)[1].split("'", 1)[0]
            items.append(Item(id=i, question=row["problem"], answer=row["answer"], topic=topic))
    return items


def heldout_ids() -> list[int]:
    """The 200 held-out question ids. Created once, then read from disk so it never shifts."""
    if SPLIT_FILE.exists():
        return json.loads(SPLIT_FILE.read_text())["ids"]
    n = len(load_all())
    ids = sorted(random.Random(SPLIT_SEED).sample(range(n), HELDOUT_SIZE))
    SPLIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_FILE.write_text(json.dumps({"seed": SPLIT_SEED, "source_rows": n, "ids": ids}, indent=1))
    return ids


def heldout() -> list[Item]:
    by_id = {it.id: it for it in load_all()}
    return [by_id[i] for i in heldout_ids()]


def dev() -> list[Item]:
    """Everything not held out; safe to use for calibration and tuning."""
    held = set(heldout_ids())
    return [it for it in load_all() if it.id not in held]


def used_dev_ids() -> set[int]:
    """Dev questions already used by earlier stages: the retrieval-tuning sample (seed 21; the full 1,000 drawn
    before filtering, to be safe), the end-to-end sample (seed 2101, 200) and the draft-diversity check (seed 3, 12)."""
    pool = dev()
    return (
        {it.id for it in random.Random(21).sample(pool, 1000)}
        | {it.id for it in random.Random(2101).sample(pool, 200)}
        | {it.id for it in random.Random(3).sample(pool, 12)}
    )


def tuning_split() -> list[Item]:
    """Stage 4 tuning split: not held out and not used by any earlier dev sample."""
    used = used_dev_ids()
    return [it for it in dev() if it.id not in used]


def tuning_sample(n: int = 60, seed: int = 4060) -> list[Item]:
    return random.Random(seed).sample(tuning_split(), n)
