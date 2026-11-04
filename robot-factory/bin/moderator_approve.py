#!/usr/bin/env python3
"""Robot Factory moderator approval tool (task 026b, 2026-11-02).

    python3 -I ~/robot-factory/bin/moderator_approve.py <task-file.md> --commission "<text>"

Per the amendment of 2026-11-01 (tiered scope approval): the MODERATOR may
approve SCOPE: build-read tasks only. This appends one record to
approvals-moderator/<name>.jsonl:
    {"t","epoch","name","target","sha256","cap_usd","approver":"moderator","commission"}
Records are appended, never edited. The runner (bin/budget.py) honours only
the LAST record, only if its sha256 equals the task file at run time and its
epoch is later than the file's last modification: any edit voids it.

Refuses: a task that is not SCOPE: build-read (build-write and legacy
SCOPE: build are Dan-only, approve.sh); a missing or empty --commission;
a run inside a seat call (RF_SEAT_RUN is set by run-next.sh for every seat).
It is a standalone tool the moderator runs between runs, never by a seat.
A cap override or APPROVAL: required in the task still needs Dan; this tool
warns about that but cannot satisfy it.
"""
import datetime, hashlib, json, os, sys, time

BASE = os.path.join(os.path.expanduser("~"), "robot-factory")
sys.path.insert(0, os.path.join(BASE, "bin"))


def die(msg, rc=2):
    print("moderator_approve: refused: %s. Nothing written." % msg, file=sys.stderr)
    sys.exit(rc)


def main(argv):
    if os.environ.get("RF_SEAT_RUN"):
        die("RF_SEAT_RUN is set: this is a seat's run; only the moderator, between runs, may approve", 1)
    if len(argv) != 3 or argv[1] != "--commission":
        print('usage: moderator_approve.py <task-file.md> --commission "<text>"', file=sys.stderr)
        sys.exit(2)
    import budget                       # the runner's own parser: one reading of the header
    f, commission = os.path.realpath(argv[0]), argv[2].strip()
    if not commission:
        die("--commission is empty: name Dan's commission this task serves")
    if not (os.path.isfile(f) and os.access(f, os.R_OK)):
        die("not a readable file: %s" % argv[0])
    if not f.endswith(".md"):
        die("task files end in .md")
    name = os.path.basename(f)[:-3]
    data = open(f, "rb").read()
    text = data.decode("utf-8")
    try:
        scope = budget.task_scope(text)
        cap, flag = budget.task_terms(text)
    except ValueError as e:
        die("task header not acceptable: %s" % e)
    if scope != "build-read":
        die("task declares %s; the moderator may approve SCOPE: build-read only "
            "(build-write and legacy SCOPE: build need Dan, approve.sh)" % scope)
    h = hashlib.sha256(data).hexdigest()
    d = os.path.join(BASE, "approvals-moderator")
    if os.path.islink(d):
        die("approvals-moderator is a symlink")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, name + ".jsonl")
    if os.path.islink(out):
        die("%s is a symlink" % out)
    ep = time.time()
    rec = {"t": datetime.datetime.fromtimestamp(ep).astimezone().isoformat(timespec="seconds"),
           "epoch": ep, "name": name, "target": f, "sha256": h, "cap_usd": cap,
           "approver": "moderator", "commission": commission}
    fd = os.open(out, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "a") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
    print("approved (moderator, build-read): %s (sha256 %s) -> %s" % (name, h[:12], out))
    if (cap is not None) or flag:
        print("warning: this task also carries %s. A cap above the default, or APPROVAL: required, "
              "still needs Dan's approval (approve.sh); this record does not cover it."
              % ("APPROVAL: required" if flag else "CAP_USD: %s" % cap), file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
