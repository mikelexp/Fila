#!/bin/bash
# Script de configuración inicial para MKVideoPlaylister

set -e

echo "=== Configurando MKVideoPlaylister ==="

# Verificar que estemos en el directorio correcto
if [ ! -f "mk_playlister.py" ]; then
    echo "Error: Ejecuta este script desde el directorio del proyecto"
    exit 1
fi

# Verificar que Python 3 esté instalado
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 no está instalado"
    exit 1
fi

# Verificar dependencias del sistema
echo "Verificando dependencias del sistema..."

if ! command -v mpv &> /dev/null; then
    echo "Advertencia: mpv no está instalado"
    echo "  Arch:          sudo pacman -S mpv"
    echo "  Ubuntu/Debian: sudo apt install mpv"
fi

if ! command -v ffprobe &> /dev/null; then
    echo "Advertencia: ffprobe no está instalado (necesario para duración de videos)"
    echo "  Arch:          sudo pacman -S ffmpeg"
    echo "  Ubuntu/Debian: sudo apt install ffmpeg"
fi

if ! ldconfig -p 2>/dev/null | grep -q libmpv; then
    echo "Advertencia: libmpv no encontrada (necesaria para el preview integrado)"
    echo "  Arch:          sudo pacman -S mpv"
    echo "  Ubuntu/Debian: sudo apt install libmpv-dev"
fi

echo "Creando entorno virtual..."
python3 -m venv venv

echo "Activando entorno virtual..."
source venv/bin/activate

echo "Actualizando pip..."
pip install --upgrade pip

echo "Instalando dependencias..."
pip install -r requirements.txt

echo ""
echo "=== Configuración completada ==="
echo ""
echo "Entorno virtual creado en: ./venv"
echo ""
echo "Para ejecutar sin compilar (desarrollo):"
echo "  ./run.sh"
echo ""
echo "Para compilar:"
echo "  ./build.sh"
echo ""
echo "Para instalar en el sistema:"
echo "  ./install.sh    (requiere haber compilado antes)"
