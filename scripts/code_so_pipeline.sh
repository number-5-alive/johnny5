#!/bin/bash
# Code shelf Q&A pipeline driver (Workstream C). Builds the Stack Overflow index on NVMe once:
#  - the SO extraction has finished,
#  - the stage 7 updater is not running, and NVMe free >= 185 GB (index ~53 GB + 130 GB reserve; Dan, 2026-10-19).
# Sister sites are scanned/extracted meanwhile; they are indexed only if the reserve still holds (checked after SO).
# code_so itself pauses during 02:30-03:30 CT.
set -euo pipefail
SE=/mnt/hub/data/code/stackexchange
DUMP=$SE/2024-04
OUT=$HOME/code-data/code-so.db
PY="nice -n 10 $HOME/laya-qwen/.venv/bin/python -m laya_qwen.code_so"
cd "$HOME/laya-qwen"
log() { echo "=== $(date '+%F %T') $*"; }
free_gb() { df -BG --output=avail / | tail -1 | tr -dc 0-9; }

log "waiting for SO extraction"
until grep -q "extract done" $SE/work-so/extract.log 2>/dev/null; do sleep 60; done
grep "extract done" $SE/work-so/extract.log

log "sister sites: waiting for downloads"
until grep -q "Download complete\|download completed" $DUMP/aria2-sister.log 2>/dev/null && ! pgrep -x aria2c >/dev/null; do sleep 60; done
(cd $DUMP && md5sum -c md5-sister.txt)
for site in askubuntu.com serverfault.com superuser.com unix.stackexchange.com; do
  W=$SE/work-$site
  [ -s $W/scan.json ] || $PY scan $DUMP $site $W
  $PY project $W | tee $W/project.txt
  grep -q "extract done" $W/extract.log 2>/dev/null || $PY extract $DUMP $site $W --workers 12 > $W/extract.log 2>&1
done

log "waiting for the updater to be idle and NVMe free >= 185 GB"
while systemctl is-active -q laya-qwen-wiki-update.service || \
      [ "$(systemctl show -p ActiveState --value laya-qwen-wiki-update.service)" = activating ] || \
      [ "$(free_gb)" -lt 185 ]; do sleep 120; done
log "building SO index (free $(free_gb) GB)"
$PY build $DUMP stackoverflow.com $SE/work-so $OUT --vintage 2024-04 --min-q-score 1 --require-answer
ls -la $OUT
log "SO_BUILD_DONE free $(free_gb) GB"
