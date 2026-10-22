#!/usr/bin/env bash
# Iniciar Cinematic YouTube Thumbnail Studio en Linux / macOS
set -e
cd "$(dirname "$0")"
echo "========================================================"
echo "  Iniciando Cinematic YouTube Thumbnail Studio..."
echo "========================================================"
if [ ! -d "node_modules" ]; then
    echo "📦 Instalando dependencias de Node.js..."
    npm install
fi
echo "🚀 Servidor web listo en: http://localhost:3000"
npm run dev -- --host 0.0.0.0 --port 3000
