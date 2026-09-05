#!/bin/bash
# Prepares the Python environment so tests and the linter run immediately.
set -euo pipefail

# Only needed in Claude Code on the web; local machines manage their own env.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

VENV=".venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r requirements-dev.txt

# Put the venv first on PATH so `pytest` and `ruff` resolve without a prefix.
{
  echo "export PATH=\"$PWD/$VENV/bin:\$PATH\""
  echo "export VIRTUAL_ENV=\"$PWD/$VENV\""
  echo "export PYTHONPATH=\"$PWD\""
} >> "${CLAUDE_ENV_FILE:-/dev/null}"

echo "session-start: environment ready ($("$VENV/bin/python" --version))"
