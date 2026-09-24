#!/bin/sh
# Shared local/CI gate. Requires requirements-dev.txt and a Python interpreter.
set -eu

cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON:-python}"

if [ "${1:-}" = '--staged' ]; then
    git diff --cached --check
fi

"$PYTHON_BIN" -m ruff check --select E4,E7,E9,F821,F822,F823 src/core src/ui tests
"$PYTHON_BIN" -m compileall -q src main.py
"$PYTHON_BIN" -m pytest -q tests
for test_file in test_*.py; do
    "$PYTHON_BIN" "$test_file" >/dev/null
done
"$PYTHON_BIN" main.py --self-test
