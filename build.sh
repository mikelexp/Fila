#!/bin/bash
# Script de compilación con Nuitka para Fila
# Genera un único binario autocontenido. Dependencias del sistema requeridas
# en la máquina destino: libmpv.so (mpv), libmpv.so (preview), ffprobe (duraciones).

set -e

echo "=== Compilando Fila con Nuitka (onefile) ==="

# Verificar que estemos en el directorio correcto
if [ ! -f "fila.py" ]; then
    echo "Error: Ejecuta este script desde el directorio del proyecto"
    exit 1
fi

# Verificar que patchelf esté instalado (requerido por Nuitka en Linux)
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
echo "Compilando con Nuitka (modo onefile)..."
echo "Esto puede tomar varios minutos..."
echo ""

# Limpiar compilaciones anteriores
rm -rf dist/fila fila.build fila.onefile-build

mkdir -p dist

# Compilar con Nuitka en modo onefile.
#
# --onefile-tempdir-spec="{CACHE_DIR}/fila"
#   Extrae a ~/.cache/fila/ la primera vez y reutiliza el caché
#   en ejecuciones posteriores (no re-extrae si el binario no cambió).
#   Esto evita la penalización de extracción en cada arranque.
#
# Dependencias que quedan fuera (del sistema):
#   - libmpv.so.2  → provista por el paquete mpv del sistema
#   - libGL / libX11 / libc / etc. → bibliotecas estándar del sistema
#   - ffprobe → ejecutable externo (detección de duración)
#   - mpv/vlc/mplayer → reproductores externos
python -m nuitka \
    --onefile \
    --onefile-tempdir-spec="{CACHE_DIR}/fila" \
    --enable-plugin=pyside6 \
    --include-qt-plugins=platforms,platformthemes,iconengines,imageformats,wayland-shell-integration,wayland-decoration-client,wayland-graphics-integration-client,xcbglintegrations \
    --include-data-files=icon.png=icon.png \
    --output-filename=fila \
    --output-dir=dist \
    --assume-yes-for-downloads \
    fila.py

echo ""
echo "=== Compilación completada ==="
echo ""
echo "Binario único creado en: ./dist/fila"
echo ""
echo "Dependencias requeridas en el sistema destino:"
echo "  - libmpv.so.2  (paquete mpv)"
echo "  - ffprobe      (paquete ffmpeg, para duración de videos)"
echo "  - mpv/vlc      (reproductores para la función Play)"
echo ""
echo "Para probarlo:"
echo "  ./dist/fila"
echo ""
echo "Para instalar en el sistema:"
echo "  ./install.sh"
