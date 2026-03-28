#!/bin/bash
# Script de instalación para MKVideoPlaylister

set -e

echo "=== Instalando MKVideoPlaylister ==="

# Verificar que el binario compilado exista
if [ ! -f "dist/mkplaylister" ]; then
    echo "Error: El binario compilado no existe"
    echo "Por favor ejecuta primero: ./build.sh"
    exit 1
fi

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

# Copiar el binario único
echo "Copiando binario a $BIN_DIR/mkplaylister..."
cp dist/mkplaylister "$BIN_DIR/mkplaylister"
chmod +x "$BIN_DIR/mkplaylister"

# Instalar el icono si existe
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
mkdir -p "$ICON_DIR"

if [ -f "mkplaylister-icon.png" ]; then
    echo "Instalando icono..."
    cp mkplaylister-icon.png "$ICON_DIR/mkplaylister.png"
    ICON_NAME="mkplaylister"
else
    ICON_NAME="multimedia-video-player"
fi

# Crear el archivo .desktop
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

echo "Creando archivo .desktop..."
cat > "$DESKTOP_DIR/mkplaylister.desktop" << EOF
[Desktop Entry]
Type=Application
Name=MK Video Playlister
Comment=Explorador de archivos multimedia con listas de reproducción
Exec=$BIN_DIR/mkplaylister
Icon=$ICON_NAME
Terminal=false
Categories=AudioVideo;Video;Player;
Keywords=video;audio;playlist;mpv;media;
EOF

echo "Archivo .desktop instalado en: $DESKTOP_DIR/mkplaylister.desktop"

# Actualizar la base de datos de aplicaciones
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$DESKTOP_DIR"
    echo "Base de datos de aplicaciones actualizada"
fi

# Actualizar el caché de iconos
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    echo "Caché de iconos actualizado"
fi

# Verificar que ~/.local/bin esté en el PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "ADVERTENCIA: $HOME/.local/bin no está en tu PATH"
    echo "Agrega esta línea a tu ~/.bashrc o ~/.zshrc:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

echo ""
echo "=== Instalación completada ==="
echo ""
echo "Ejecutable instalado en: $BIN_DIR/mkplaylister"
echo "Caché de extracción en:  ~/.cache/mkplaylister/"
echo ""
echo "Para ejecutar:"
echo "  mkplaylister"
echo ""
echo "Para desinstalar:"
echo "  rm $BIN_DIR/mkplaylister"
echo "  rm -rf ~/.cache/mkplaylister"
echo "  rm $DESKTOP_DIR/mkplaylister.desktop"
