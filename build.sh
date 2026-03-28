#!/bin/bash
# Script de compilación con Nuitka para MKVideoPlaylister

set -e

echo "=== Compilando MKVideoPlaylister con Nuitka ==="

# Verificar que estemos en el directorio correcto
if [ ! -f "mk_playlister.py" ]; then
    echo "Error: Ejecuta este script desde el directorio del proyecto"
    exit 1
fi

# Verificar que patchelf esté instalado
if ! command -v patchelf &> /dev/null; then
    echo "Error: patchelf no está instalado"
    echo ""
    echo "  Arch:          sudo pacman -S patchelf"
    echo "  Ubuntu/Debian: sudo apt install patchelf"
    echo "  Fedora/RHEL:   sudo dnf install patchelf"
    exit 1
fi

# Verificar que el entorno virtual exista
if [ ! -d "venv" ]; then
    echo "Error: El entorno virtual no existe"
    echo "Por favor ejecuta primero: ./setup.sh"
    exit 1
fi

# Activar entorno virtual
source venv/bin/activate

# Verificar que Nuitka esté instalado
if ! python -c "import nuitka" 2>/dev/null; then
    echo "Instalando Nuitka y dependencias de desarrollo..."
    pip install -r requirements-dev.txt
fi

echo ""
echo "Compilando con Nuitka..."
echo "Esto puede tomar varios minutos..."
echo ""

# Limpiar compilaciones anteriores
rm -rf dist/mkplaylister.dist mkplaylister.build mkplaylister.onefile-build

# Compilar con Nuitka (modo standalone)
python -m nuitka \
    --standalone \
    --enable-plugin=pyside6 \
    --output-filename=mkplaylister \
    --output-dir=dist \
    --assume-yes-for-downloads \
    mk_playlister.py

echo ""
echo "=== Compilación completada ==="
echo ""
echo "Ejecutable creado en: ./dist/mkplaylister.dist/mkplaylister"
echo ""
echo "Para probarlo:"
echo "  ./dist/mkplaylister.dist/mkplaylister"
echo ""
echo "Para instalar en el sistema:"
echo "  ./install.sh"
