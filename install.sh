#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
DESKTOP_DIR="$HOME/.local/share/applications"

if [ -f "$SCRIPT_DIR/fila" ]; then
    BIN_SOURCE="$SCRIPT_DIR/fila"
elif [ -f "$SCRIPT_DIR/dist/fila.bin" ]; then
    BIN_SOURCE="$SCRIPT_DIR/dist/fila.bin"
else
    echo "Error: no se encontró el binario de Fila."
    echo "Ejecuta primero: ./build.sh"
    exit 1
fi

mkdir -p "$BIN_DIR" "$ICON_DIR" "$DESKTOP_DIR"

cp "$BIN_SOURCE" "$BIN_DIR/fila"
chmod +x "$BIN_DIR/fila"

if [ -f "$SCRIPT_DIR/icon.png" ]; then
    cp "$SCRIPT_DIR/icon.png" "$ICON_DIR/fila.png"
    ICON_NAME="fila"
else
    ICON_NAME="multimedia-video-player"
fi

cat > "$DESKTOP_DIR/fila.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Fila
Comment=Browse folders, filter media, generate playlists, and play files
Exec=$BIN_DIR/fila
Icon=$ICON_NAME
Terminal=false
Categories=AudioVideo;Video;Player;
Keywords=video;audio;playlist;mpv;media;
StartupNotify=true
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "ADVERTENCIA: $HOME/.local/bin no está en tu PATH"
fi

echo "Fila instalado en: $BIN_DIR/fila"
