#!/usr/bin/env bash
# PostToolUse(Edit|Write): when a src/instream module is edited, run its matching
# tests/test_<module>.py if one exists. Never blocks (always exits 0).
. "$(dirname "$0")/_lib.sh"

fp=$(hook_file_path)
if printf '%s' "$fp" | grep -qE 'src/instream/.*\.py$'; then
  root=${fp%%/src/instream/*}
  module=$(basename "$fp" .py)
  testfile="$root/tests/test_${module}.py"
  if [ -f "$testfile" ]; then
    micromamba run -n shiny python -m pytest "$testfile" -x -q 2>&1 | tail -n 5
  fi
fi
exit 0
