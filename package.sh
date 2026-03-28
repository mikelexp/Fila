#!/bin/bash
# Script para crear paquete de distribución de MKVideoPlaylister

set -e

echo "=== Empaquetando MKVideoPlaylister para distribución ==="

if [ ! -f "install.sh" ]; then
    echo "Error: Ejecuta este script desde el directorio del proyecto"
    exit 1
fi

if [ ! -f "dist/mkplaylister" ]; then
    echo "Error: El binario no existe"
    echo "Por favor ejecuta primero: ./build.sh"
    exit 1
fi

PACKAGE_NAME="mkplaylister-$(date +%Y%m%d-%H%M%S)"
TEMP_DIR="/tmp/$PACKAGE_NAME"

echo "Creando directorio temporal: $TEMP_DIR"
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

echo "Copiando binario..."
cp dist/mkplaylister "$TEMP_DIR/"
chmod +x "$TEMP_DIR/mkplaylister"

echo "Copiando script de instalación..."
cp install.sh "$TEMP_DIR/"
chmod +x "$TEMP_DIR/install.sh"

if [ -f "mkplaylister-icon.png" ]; then
    echo "Copiando icono..."
    cp mkplaylister-icon.png "$TEMP_DIR/"
fi

cat > "$TEMP_DIR/README.txt" << 'EOF'
# MK Video Playlister

Explorador de archivos multimedia con preview integrado y listas de reproducción m3u8.
Binario único autocontenido — no requiere Python ni dependencias adicionales.

## Dependencias del sistema requeridas

  Arch:          sudo pacman -S mpv ffmpeg
  Ubuntu/Debian: sudo apt install mpv libmpv-dev ffmpeg

## Instalación

  tar -xzf mkplaylister-*.tar.gz
  cd mkplaylister-*/
  ./install.sh

## Desinstalación

  rm ~/.local/bin/mkplaylister
  rm -rf ~/.cache/mkplaylister
  rm ~/.local/share/applications/mkplaylister.desktop
EOF

ORIGINAL_DIR="$(pwd)"
OUTPUT_FILE="$PACKAGE_NAME.tar.gz"

echo "Creando tarball: $OUTPUT_FILE"
cd /tmp
tar -czf "$OUTPUT_FILE" "$PACKAGE_NAME/"
mv "$OUTPUT_FILE" "$ORIGINAL_DIR/"
cd "$ORIGINAL_DIR"

rm -rf "$TEMP_DIR"

echo ""
echo "=== Empaquetado completado ==="
echo ""
echo "Paquete: $OUTPUT_FILE"
echo "Tamaño:  $(du -h "$OUTPUT_FILE" | cut -f1)"
