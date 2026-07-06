#!/usr/bin/env bash
# PreToolUse(Edit|Write): refuse to edit secrets/credentials and generated/cached
# files. Exit code 2 blocks the tool call; the stderr message is shown to Claude.
. "$(dirname "$0")/_lib.sh"

fp=$(hook_file_path)

if printf '%s' "$fp" | grep -qE '\.(env|pem|key|secret)$'; then
  echo "BLOCK: refusing to edit sensitive file ($fp)" >&2
  exit 2
fi
if printf '%s' "$fp" | grep -qE '(^|/)(\.env|credentials|secrets)'; then
  echo "BLOCK: refusing to edit sensitive file ($fp)" >&2
  exit 2
fi
if printf '%s' "$fp" | grep -qE '(__pycache__|\.benchmarks|\.hypothesis|\.lock$)'; then
  echo "BLOCK: refusing to edit generated/cached file ($fp)" >&2
  exit 2
fi
exit 0
