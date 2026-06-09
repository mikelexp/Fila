#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
    bash "$ROOT_DIR/scripts/install-build-deps.sh"
fi

if ! "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info[:2] <= (3, 13) else 1)
PY
then
    echo "Venv incompatible; recreating with python3.13"
    rm -rf "$ROOT_DIR/venv"
    PYTHON_CMD="${PYTHON_CMD:-python3.13}" bash "$ROOT_DIR/scripts/install-build-deps.sh"
fi

exec "$PYTHON_BIN" "$ROOT_DIR/build_nuitka.py" --clean
