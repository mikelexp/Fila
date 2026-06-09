#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-${VERSION:-}}"

if [ -z "$VERSION" ]; then
    VERSION="$(git -C "$ROOT_DIR" describe --tags --abbrev=0 --match 'v*' 2>/dev/null || true)"
    VERSION="${VERSION#v}"
fi

if [ -z "$VERSION" ]; then
    VERSION="snapshot"
fi

if [ ! -f "$ROOT_DIR/dist/fila.bin" ]; then
    echo "Error: dist/fila.bin no existe"
    echo "Ejecuta primero: make build-onefile"
    exit 1
fi

RELEASE_DIR="$ROOT_DIR/release"
ARCHIVE_NAME="fila-${VERSION}-linux-x86_64.tar.gz"

rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

cp "$ROOT_DIR/dist/fila.bin" "$RELEASE_DIR/fila"
cp "$ROOT_DIR/icon.png" "$RELEASE_DIR/"
cp "$ROOT_DIR/install.sh" "$RELEASE_DIR/"
chmod +x "$RELEASE_DIR/fila" "$RELEASE_DIR/install.sh"

cat > "$RELEASE_DIR/fila.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Fila
Comment=Browse folders, filter media, generate playlists, and play files
Exec=fila
Icon=fila
Categories=AudioVideo;Video;Player;
Terminal=false
StartupNotify=true
EOF

tar -czf "$ROOT_DIR/$ARCHIVE_NAME" -C "$RELEASE_DIR" fila icon.png fila.desktop install.sh

echo "Creado: $ROOT_DIR/$ARCHIVE_NAME"
