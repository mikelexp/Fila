#!/bin/bash
# Script para ejecutar MKVideoPlaylister sin compilar (desarrollo)

set -e

# Verificar que estemos en el directorio correcto
if [ ! -f "mk_playlister.py" ]; then
    echo "Error: Ejecuta este script desde el directorio del proyecto"
    exit 1
fi

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo "Entorno virtual no encontrado. Creándolo..."

    if ! command -v python3 &> /dev/null; then
        echo "Error: Python 3 no está instalado"
        exit 1
    fi

    python3 -m venv venv
    echo "Entorno virtual creado."
fi

# Asegurar que pip esté disponible
if [ ! -f "venv/bin/pip" ]; then
    echo "pip no encontrado. Reinstalando..."
    python3 -m venv venv --clear
fi

# Verificar si las dependencias están instaladas
if ! ./venv/bin/python -c "import PySide6; import mpv" 2>/dev/null; then
    echo "Dependencias no encontradas. Instalando..."
    ./venv/bin/pip install -q --upgrade pip setuptools wheel
    ./venv/bin/pip install -q -r requirements.txt
    echo "Dependencias instaladas."
fi

# Ejecutar la aplicación
exec ./venv/bin/python mk_playlister.py "$@"
