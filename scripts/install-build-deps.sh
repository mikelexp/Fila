#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_CMD="${PYTHON_CMD:-python3.13}"

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    for candidate in python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_CMD="$candidate"
            break
        fi
    done
fi

PYTHON_BIN="$VENV_DIR/bin/python"

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    echo "Error: no se encontró un Python compatible (ideal: python3.13)"
    exit 1
fi

for cmd in mpv ffprobe patchelf; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        case "$cmd" in
            mpv)
                echo "Advertencia: mpv no está instalado"
                ;;
            ffprobe)
                echo "Advertencia: ffprobe no está instalado"
                ;;
            patchelf)
                echo "Advertencia: patchelf no está instalado"
                ;;
        esac
    fi
done

if ! ldconfig -p 2>/dev/null | grep -q libmpv; then
    echo "Advertencia: libmpv no apareció en ldconfig"
fi

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r "$ROOT_DIR/requirements.txt" -r "$ROOT_DIR/requirements-dev.txt"

echo "Entorno listo en: $VENV_DIR"
