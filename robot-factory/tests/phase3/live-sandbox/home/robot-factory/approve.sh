#!/usr/bin/env bash
# Robot Factory approval tool (Phase 2, task 006, 2026-10-31). Draft for Dan.
#
#   approve.sh <task-file.md>
#
# Dan's ruling Q1: interactive-only. This refuses to run unless stdin AND
# stdout are a terminal, so headless sessions (the seat's, Alex's) cannot
# use it. It shows the task, its sha256 and any CAP_USD line, asks Dan to
# type "approve", and appends one record to approvals/<name>.jsonl:
#   {"t","epoch","name","target","sha256","cap_usd","tty","user"}
# The runner (bin/budget.py) honours only the LAST record for a task, and
# only if its sha256 equals the file as it stands at run time and its
# epoch is later than the file's last modification. Any edit to the task
# after approving it voids the approval; run this again to re-approve.
# Records are appended, never edited.
set -uo pipefail
if [ ! -t 0 ] || [ ! -t 1 ]; then
  echo "approve.sh: refused: stdin and stdout must both be a terminal (interactive-only, Q1). Nothing written." >&2
  exit 1
fi
BASE="$HOME/robot-factory"
[ $# -eq 1 ] || { echo "usage: approve.sh <task-file.md>"; exit 2; }
f=$(readlink -f -- "$1") || { echo "approve.sh: no such file: $1"; exit 2; }
[ -f "$f" ] && [ -r "$f" ] || { echo "approve.sh: not a readable file: $1"; exit 2; }
case "$f" in *.md) ;; *) echo "approve.sh: task files end in .md"; exit 2;; esac
name=$(basename "$f" .md)
hash=$(sha256sum -- "$f" | cut -d' ' -f1)
cap=$(grep -m1 '^CAP_USD:' -- "$f" || true)
echo "----- $f -----"
cat -- "$f"
echo "----- end of file -----"
echo "task:    $name"
echo "sha256:  $hash"
echo "cap:     ${cap:-none (budget.yaml default)}"
grep -qx 'APPROVAL: required' -- "$f" && echo "flag:    APPROVAL: required"
printf 'Type "approve" to approve exactly this file as it stands: '
read -r answer < /dev/tty || answer=
[ "$answer" = approve ] || { echo "not approved. Nothing written."; exit 1; }
# Re-hash after the prompt: if the file changed while Dan was reading, refuse.
hash2=$(sha256sum -- "$f" | cut -d' ' -f1)
[ "$hash2" = "$hash" ] || { echo "approve.sh: file changed while you were reading it. Nothing written."; exit 1; }
mkdir -p "$BASE/approvals"
python3 -I - "$BASE/approvals/$name.jsonl" "$name" "$f" "$hash" "${cap#CAP_USD: }" "$(tty)" "${USER:-?}" <<'PY'
import datetime, json, sys, time
out, name, target, h, cap, tty, user = sys.argv[1:]
ep = time.time()
rec = {"t": datetime.datetime.fromtimestamp(ep).astimezone().isoformat(timespec="seconds"),
       "epoch": ep, "name": name, "target": target, "sha256": h,
       "cap_usd": float(cap) if cap.replace(".", "", 1).isdigit() else None,
       "tty": tty, "user": user}
with open(out, "a") as f:
    f.write(json.dumps(rec, separators=(",", ":")) + "\n")
print("approved: %s (sha256 %s) -> %s" % (name, h[:12], out))
PY
