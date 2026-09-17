#!/usr/bin/env bash
# ==============================================================================
# Unit Test Suite Runner (Fast Parallel Python Test Runner)
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PYTHON_BIN="python3"
if [ -x "$REPO_ROOT/.python_env/bin/python3" ]; then
    PYTHON_BIN="$REPO_ROOT/.python_env/bin/python3"
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/run_unit_parallel.py" "$@"
