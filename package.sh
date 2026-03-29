#!/bin/bash
# Script para crear paquete de distribución de Fila

set -e

echo "=== Empaquetando Fila para distribución ==="

if [ ! -f "install.sh" ]; then
    echo "Error: Ejecuta este script desde el directorio del proyecto"
    exit 1
fi

if [ ! -f "dist/fila" ]; then
    echo "Error: El binario no existe"
    echo "Por favor ejecuta primero: ./build.sh"
    exit 1
fi

PACKAGE_NAME="fila-$(date +%Y%m%d-%H%M%S)"
TEMP_DIR="/tmp/$PACKAGE_NAME"

echo "Creando directorio temporal: $TEMP_DIR"
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

echo "Copiando binario..."
cp dist/fila "$TEMP_DIR/"
chmod +x "$TEMP_DIR/fila"

echo "Copiando script de instalación..."
cp install.sh "$TEMP_DIR/"
chmod +x "$TEMP_DIR/install.sh"

if [ -f "icon.png" ]; then
    echo "Copiando icono..."
    cp icon.png "$TEMP_DIR/"
fi

cat > "$TEMP_DIR/README.txt" << 'EOF'
# Fila

Explorador de archivos multimedia con preview integrado y listas de reproducción m3u8.
Binario único autocontenido — no requiere Python ni dependencias adicionales.

## Dependencias del sistema requeridas

  Arch:          sudo pacman -S mpv ffmpeg
  Ubuntu/Debian: sudo apt install mpv libmpv-dev ffmpeg

## Instalación

  tar -xzf fila-*.tar.gz
  cd fila-*/
  ./install.sh

## Desinstalación

  rm ~/.local/bin/fila
  rm -rf ~/.cache/fila
  rm ~/.local/share/applications/fila.desktop
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
