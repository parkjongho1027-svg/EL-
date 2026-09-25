#!/bin/sh
# Shared local/CI gate. Requires requirements-dev-lock.txt and a Python interpreter.
set -eu

cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON:-python}"

if [ "${1:-}" = '--staged' ]; then
    git diff --cached --check
fi

"$PYTHON_BIN" -m ruff check --extend-exclude tests/legacy --select E4,E7,E9,F821,F822,F823 src/core src/ui tests
"$PYTHON_BIN" -m ruff check --select F821,F822,F823 main.py src/config src/persistence src/diagnostics
"$PYTHON_BIN" -m compileall -q src main.py
"$PYTHON_BIN" -m pytest -q tests --cov=src.core --cov-branch --cov-report=term --cov-fail-under=90
"$PYTHON_BIN" main.py --self-test
