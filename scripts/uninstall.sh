#!/bin/bash
set -euo pipefail

PURGE=false
for arg in "$@"; do
    if [ "$arg" = "--purge" ]; then
        PURGE=true
    fi
done

BIN_DIR="$HOME/.local/bin"
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
DESKTOP_FILE="$HOME/.local/share/applications/fila.desktop"

rm -f "$BIN_DIR/fila" "$DESKTOP_FILE" "$ICON_DIR/fila.png"

if [ "$PURGE" = true ]; then
    rm -rf "$HOME/.cache/fila" "$HOME/.config/fila"
fi

echo "Fila desinstalado"
