#!/usr/bin/env bash
# Phase 11 sandbox tests (task 033): budget.py project, the read-only
# projection meter. A throwaway fake factory under tests/phase11/sandbox/,
# the real budget.py, budget.yaml and registry copied in, and the live ledger
# copied in WITHOUT its 024s1-saint-economics lines (leave-one-out history).
# The live budget.yaml, ledger.jsonl and registry are only READ (sha-checked).
# No model is called.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
exec python3 -I "$HERE/test_project.py" "$HERE"
