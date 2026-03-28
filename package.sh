#!/bin/bash
# Script para crear paquete de distribución de MKVideoPlaylister

set -e

echo "=== Empaquetando MKVideoPlaylister para distribución ==="

# Verificar que estemos en el directorio correcto
if [ ! -f "install.sh" ]; then
    echo "Error: Ejecuta este script desde el directorio del proyecto"
    exit 1
fi

# Verificar que la aplicación esté compilada
if [ ! -d "dist/mkplaylister.dist" ]; then
    echo "Error: La aplicación no está compilada"
    echo "Por favor ejecuta primero: ./build.sh"
    exit 1
fi

# Crear directorio temporal
PACKAGE_NAME="mkplaylister-$(date +%Y%m%d-%H%M%S)"
TEMP_DIR="/tmp/$PACKAGE_NAME"

echo "Creando directorio temporal: $TEMP_DIR"
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Copiar ejecutable compilado
echo "Copiando ejecutable compilado..."
cp -r dist/mkplaylister.dist "$TEMP_DIR/"

# Copiar script de instalación
echo "Copiando script de instalación..."
cp install.sh "$TEMP_DIR/"
chmod +x "$TEMP_DIR/install.sh"

# Copiar icono si existe
if [ -f "mkplaylister-icon.png" ]; then
    echo "Copiando icono..."
    cp mkplaylister-icon.png "$TEMP_DIR/"
fi

# Crear README de instalación
cat > "$TEMP_DIR/README.txt" << 'EOF'
# MK Video Playlister

Explorador de archivos multimedia con preview integrado y listas de reproducción m3u8.

## Dependencias del sistema requeridas

- mpv y libmpv (para el preview integrado)
- ffmpeg/ffprobe (para obtener la duración de los videos)

  Arch:          sudo pacman -S mpv ffmpeg
  Ubuntu/Debian: sudo apt install mpv libmpv-dev ffmpeg

## Instalación

1. Extraer el archivo:
   tar -xzf mkplaylister-*.tar.gz
   cd mkplaylister-*/

2. Ejecutar el instalador:
   ./install.sh

## Uso

  mkplaylister

## Desinstalación

  rm ~/.local/bin/mkplaylister
  rm -rf ~/.local/share/mkplaylister
  rm ~/.local/share/applications/mkplaylister.desktop
  update-desktop-database ~/.local/share/applications
EOF

# Crear el tarball
ORIGINAL_DIR="$(pwd)"
OUTPUT_FILE="$PACKAGE_NAME.tar.gz"

echo "Creando tarball: $OUTPUT_FILE"
cd /tmp
tar -czf "$OUTPUT_FILE" "$PACKAGE_NAME/"
mv "$OUTPUT_FILE" "$ORIGINAL_DIR/"
cd "$ORIGINAL_DIR"

# Limpiar
echo "Limpiando archivos temporales..."
rm -rf "$TEMP_DIR"

echo ""
echo "=== Empaquetado completado ==="
echo ""
echo "Paquete creado: $OUTPUT_FILE"
echo "Tamaño: $(du -h "$OUTPUT_FILE" | cut -f1)"
