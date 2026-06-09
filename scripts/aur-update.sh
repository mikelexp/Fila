#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_SLUG="${REPO_SLUG:-mikelexp/Fila}"
AUR_REPO_URL="${AUR_REPO_URL:-ssh://aur@aur.archlinux.org/fila-bin.git}"
VERSION="${1:-${VERSION:-}}"

if [ -z "$VERSION" ]; then
    if command -v gh >/dev/null 2>&1; then
        VERSION="$(gh release view --repo "$REPO_SLUG" --json tagName --jq .tagName 2>/dev/null || true)"
    fi
fi

VERSION="${VERSION#v}"

if [ -z "$VERSION" ]; then
    echo "Error: no se pudo determinar la versión. Pasa VERSION=... o un tag publicado."
    exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ARCHIVE_NAME="fila-${VERSION}-linux-x86_64.tar.gz"
ARCHIVE_URL="https://github.com/${REPO_SLUG}/releases/download/v${VERSION}/${ARCHIVE_NAME}"
ARCHIVE_PATH="$TMP_DIR/$ARCHIVE_NAME"
AUR_DIR="$TMP_DIR/fila-bin"

if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE_PATH"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$ARCHIVE_PATH" "$ARCHIVE_URL"
else
    echo "Error: necesitas curl o wget"
    exit 1
fi

SHA256="$(sha256sum "$ARCHIVE_PATH" | awk '{print $1}')"

git clone "$AUR_REPO_URL" "$AUR_DIR"

cat > "$AUR_DIR/PKGBUILD" <<EOF
# Maintainer: Mikele <mikele@gmail.com>

pkgname=fila-bin
pkgver=$VERSION
pkgrel=1
pkgdesc="Browse folders, filter media, generate playlists, and play files"
arch=('x86_64')
url="https://github.com/${REPO_SLUG}"
depends=('mpv' 'ffmpeg' 'xdg-utils')
source=("${ARCHIVE_URL}")
sha256sums=('$SHA256')

package() {
  cd "\$srcdir"

  install -Dm755 fila "\$pkgdir/usr/bin/fila"
  install -Dm644 icon.png "\$pkgdir/usr/share/icons/hicolor/512x512/apps/fila.png"
  install -Dm644 fila.desktop "\$pkgdir/usr/share/applications/fila.desktop"
}
EOF

(cd "$AUR_DIR" && makepkg --printsrcinfo > .SRCINFO)

git -C "$AUR_DIR" add PKGBUILD .SRCINFO
if git -C "$AUR_DIR" diff --cached --quiet; then
    echo "AUR ya estaba actualizado"
    exit 0
fi

git -C "$AUR_DIR" commit -m "Update to v$VERSION"
git -C "$AUR_DIR" push

echo "AUR actualizado para v$VERSION"
