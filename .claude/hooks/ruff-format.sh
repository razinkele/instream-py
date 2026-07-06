#!/usr/bin/env bash
# PostToolUse(Edit|Write): lint-fix and format edited Python files with ruff
# from the `shiny` micromamba env. Never blocks (always exits 0).
. "$(dirname "$0")/_lib.sh"

fp=$(hook_file_path)
if printf '%s' "$fp" | grep -qE '\.py$'; then
  micromamba run -n shiny ruff check --fix --quiet "$fp" 2>/dev/null
  micromamba run -n shiny ruff format --quiet "$fp" 2>/dev/null
fi
exit 0
