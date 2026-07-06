#!/usr/bin/env bash
# Shared helper for Claude Code Edit|Write hooks.
# Reads the hook's JSON payload from stdin and prints the edited file path,
# with Windows backslash separators normalized to forward slashes so that
# forward-slash regexes (e.g. src/instream/) match on this machine.
hook_file_path() {
  local input fp
  input=$(cat)
  fp=$(printf '%s' "$input" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
  printf '%s' "$fp" | sed 's#\\\\#/#g'
}
