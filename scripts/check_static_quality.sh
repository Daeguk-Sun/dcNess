#!/bin/sh
# Run the same Python static quality gates used by CI.

set -eu

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  else
    PYTHON_BIN="python3"
  fi
fi

"$PYTHON_BIN" -m ruff check .
"$PYTHON_BIN" -m mypy
"$PYTHON_BIN" -m bandit -c pyproject.toml -r harness scripts -l -i
