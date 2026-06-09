#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rm -rf \
    "$ROOT_DIR/build" \
    "$ROOT_DIR/dist" \
    "$ROOT_DIR/__pycache__" \
    "$ROOT_DIR/fila.build" \
    "$ROOT_DIR/fila.dist" \
    "$ROOT_DIR/fila.onefile-build" \
    "$ROOT_DIR/fila.bin"
