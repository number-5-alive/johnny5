"""Hang glider contract suite (029). Non-interactive; exits 0 when every check passes, 1 otherwise.

  python scripts/hangglider_contract.py                    # stubbed model, through the HTTP app (default)
  python scripts/hangglider_contract.py --live             # same checks, one run against local Ollama
  python scripts/hangglider_contract.py --records DIR      # same checks over records already written (e.g. smokes)

The stubbed run goes through the real FastAPI app (/v1/models, /v1/chat/completions) with ollama.chat replaced, so
the card checked is the mode's real output, not a fixture. Records, logs and config go to a temp dir.
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hangglider-contract-"))
os.environ.setdefault("HANGGLIDER_RECORDS", str(TMP / "records"))
os.environ.setdefault("LAYA_QWEN_SERVICE_LOG", str(TMP / "log"))
os.environ.setdefault("LAYA_QWEN_SERVICE_CONFIG", str(TMP / "service.json"))
if not Path(os.environ["LAYA_QWEN_SERVICE_CONFIG"]).exists():
    Path(os.environ["LAYA_QWEN_SERVICE_CONFIG"]).write_text(json.dumps({"phoenix": {"enabled": False}}))

from laya_qwen import hangglider, ollama, service  # noqa: E402

# The stamp strings, spelled independently of the code under test.
STAMPS = ("✅ Verified", "no malfunction")
REQUEST = "How might a library get teenagers to visit?"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


# --- stub model ---------------------------------------------------------------------------------------------------

STUB_DIRECTIONS = ["late-night silent disco in the stacks", "trading-card economy for overdue fines",
                   "lichen-style slow growth through school clubs", "ask teens to secretly redesign the place",
                   "honest hustle: teach persuasion workshops"]


def stub_chat(messages, *, think, options=None, model=None, timeout=None, format=None):
    prompt = messages[-1]["content"]
    if format is not None:  # the reassessment
        body = {"attractor": "run more events and advertise them on social media",
                "set_aside": "Set aside: the events-and-ads consensus, which any planner would propose.",
                "clusters": [{"drafts": [2, 4], "mechanism": "teens own the rules", "ignores": "staff workload"},
                             {"drafts": [3, 5], "mechanism": "slow social spread", "ignores": "measurable reach"}],
                "recombination": {"elements": [{"draft": 2, "element": "card economy"},
                                               {"draft": 4, "element": "teen redesign"}],
                                  "combined_mechanism": "teens design the card economy that runs the library",
                                  "workable": True, "beats_best_single_on_novelty": True, "reasoning": "stub"},
                "best_single": {"draft": 4, "mechanism": "teen redesign", "why_furthest": "stub"},
                "decision": "combination",
                "pick": {"mechanism": "teens design the card economy", "ignores": "adult patrons",
                         "why_survived": "no single draft combined ownership with an economy",
                         "parentage": [{"draft": 2, "contributed": "card economy"},
                                       {"draft": 4, "contributed": "teen redesign"}]},
                "final_draft": "Hand the teenagers the keys to a card economy they design. (stub final; "
                               "this stub also says no malfunction and ✅ Verified to prove the guard holds)"}
        return ollama.ChatResult(json.dumps(body), "", 50, 500, 0.01, "stop")
    n = prompt.count("\n- ")  # taken-list lines so far
    text = (f"Stub draft at temperature {options['temperature']}. Words words library teen idea {n}.\n"
            f"Direction: {STUB_DIRECTIONS[n % len(STUB_DIRECTIONS)]}")
    return ollama.ChatResult(text, "", 40, 200, 0.01, "stop")


# --- the checks (shared by stub, live and records modes) ----------------------------------------------------------


def check_card(card: str, tag: str) -> None:
    details = re.findall(r"<details\b[^>]*>", card)
    check(f"{tag}card: final draft present on top, labelled '{hangglider.LABEL}'",
          card.startswith(f"**{hangglider.LABEL}**\n\n") and len(card.split("<details", 1)[0].strip()) > 40)
    check(f"{tag}card: exactly three <details> sections", len(details) == 3 and card.count("</details>") == 3,
          f"found {len(details)}")
    check(f"{tag}card: all <details> collapsed (no 'open' attribute)",
          all(not re.search(r"\bopen\b", d) for d in details), "; ".join(details))
    summaries = re.findall(r"<summary>(.*?)</summary>", card)
    check(f"{tag}card: bands in order conservative/middle/liberal",
          [s.split()[0] for s in summaries] == ["conservative", "middle", "liberal"], " | ".join(summaries))
    check(f"{tag}card: nothing after the third section", card.rstrip().endswith("</details>"))
    found = [s for s in STAMPS if s.lower() in card.lower()]
    check(f"{tag}stamp absence: card contains neither stamp string", not found, f"found {found}")


def check_record(rec: dict, tag: str) -> None:
    d = rec.get("drafts", [])
    check(f"{tag}record: five drafts in full", len(d) == 5 and all(x.get("text", "").strip() for x in d))
    check(f"{tag}record: five temperatures", len([x["temperature"] for x in d if "temperature" in x]) == 5,
          str([x.get("temperature") for x in d]))
    check(f"{tag}record: five angles", len({x.get("angle") for x in d if x.get("angle")}) == 5,
          str([x.get("angle") for x in d]))
    check(f"{tag}record: request, clusters, reasoning verbatim, pick, band representatives",
          rec.get("request") and rec.get("clusters") is not None and rec.get("reassessment", {}).get("raw")
          and rec.get("pick") and set(rec.get("band_representatives", {})) == {"conservative", "middle", "liberal"})
    if rec.get("sweep") is None:
        check(f"{tag}record: normal ladder 0.2/0.6/1.0/1.5/1.9", rec.get("ladder") == hangglider.LADDER,
              str(rec.get("ladder")))
    att, aside = rec.get("attractor") or "", rec.get("set_aside") or ""
    check(f"{tag}attractor named and explicitly set aside",
          len(att.strip()) > 5 and aside.lower().startswith("set aside"), f"attractor={att[:80]!r}")
    growth_ok, why = True, []
    for k, x in enumerate(d):
        prior = [y["direction"] for y in d[:k]]
        if x.get("taken_list") != prior or not all(p in x.get("brief", "") for p in prior):
            growth_ok = False
            why.append(f"draft {k + 1}")
    check(f"{tag}taken-list growth: draft n's brief names directions of drafts 1..n-1",
          growth_ok and [len(x.get("taken_list", [])) for x in d] == [0, 1, 2, 3, 4], ", ".join(why))
    reps = rec.get("band_representatives", {})
    check(f"{tag}band representatives drawn from their bands",
          reps.get("conservative", {}).get("draft") in (1, 2) and reps.get("middle", {}).get("draft") == 3
          and reps.get("liberal", {}).get("draft") in (4, 5), json.dumps(reps))


# --- modes -------------------------------------------------------------------------------------------------------


def stub_suite() -> None:
    from fastapi.testclient import TestClient
    ollama.chat = stub_chat
    client = TestClient(service.app)
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    check("advertised: /v1/models lists hangglider beside the existing modes",
          "hangglider" in ids and {"grasshopper", "butterfly", "input"} <= set(ids), str(ids))
    for stream in (False, True):
        tag = f"[{'stream' if stream else 'json'}] "
        before = set(Path(os.environ["HANGGLIDER_RECORDS"]).glob("*.json"))
        r = client.post("/v1/chat/completions", json={"model": "hangglider", "stream": stream,
                                                       "messages": [{"role": "user", "content": REQUEST}]})
        if stream:
            card = "".join(json.loads(l[6:])["choices"][0]["delta"].get("content", "") or ""
                           for l in r.text.splitlines() if l.startswith("data: {"))
        else:
            card = r.json()["choices"][0]["message"]["content"]
        check_card(card, tag)
        new = set(Path(os.environ["HANGGLIDER_RECORDS"]).glob("*.json")) - before
        check(f"{tag}record: exactly one record file written for the run", len(new) == 1, str(new))
        if new:
            rec = json.loads(next(iter(new)).read_text())
            check_record(rec, tag)
            check(f"{tag}stamp guard: injected stamp strings were removed and recorded",
                  sorted(rec["stamp_strings_removed"]) == sorted(STAMPS), str(rec["stamp_strings_removed"]))
    # Sweep engages (one smoke): the top rung steps 2.0 -> 2.25 across runs, the rest of the ladder is untouched.
    os.environ["HANGGLIDER_SWEEP"] = "1"
    sweep_dir = TMP / "sweep"
    l1, s1 = hangglider.ladder_for_run(sweep_dir)
    l2, s2 = hangglider.ladder_for_run(sweep_dir)
    del os.environ["HANGGLIDER_SWEEP"]
    l0, s0 = hangglider.ladder_for_run(sweep_dir)
    check("sweep: off by default, fixed ladder", s0 is None and l0 == [0.2, 0.6, 1.0, 1.5, 1.9], str(l0))
    check("sweep: engages, top rung steps 2.0 then 2.25, lower rungs fixed",
          l1 == [0.2, 0.6, 1.0, 1.5, 2.0] and l2 == [0.2, 0.6, 1.0, 1.5, 2.25], f"{l1} {l2}")
    check("angle bank: data list with the seven required seats, cycling",
          {"behavioral economist", "game designer", "biologist", "curious 12-year-old", "cheerful con artist",
           "retired circus ringmaster", "mycologist"} <= {a["seat"] for a in hangglider.ANGLE_BANK}
          and hangglider.angle_for(len(hangglider.ANGLE_BANK))["seat"] == hangglider.ANGLE_BANK[0]["seat"])


def records_suite(paths: list[Path]) -> None:
    for p in paths:
        rec = json.loads(p.read_text())
        tag = f"[{p.name}] "
        check_card(rec["card"], tag)
        check_record(rec, tag)


def main() -> int:
    args = sys.argv[1:]
    if "--records" in args:
        d = Path(args[args.index("--records") + 1])
        records_suite(sorted(d.glob("*.json")))
    elif "--live" in args:
        card, rec, path = hangglider.run(REQUEST)
        check_card(card, "[live] ")
        check_record(rec, "[live] ")
        print(f"record: {path}")
    else:
        stub_suite()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   ({detail})" if detail and not ok else ""))
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} checks passed" + (f", {failed} FAILED" if failed else ""))
    return 1 if failed or not results else 0


if __name__ == "__main__":
    sys.exit(main())
