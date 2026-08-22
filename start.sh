#!/bin/bash
# AgentKit — Script de inicio
# El usuario ejecuta: bash start.sh

set -e

echo ""
echo "==========================================================="
echo "   AgentKit — WhatsApp AI Agent Builder"
echo "==========================================================="
echo ""
echo "  Preparando tu entorno para construir tu agente de IA..."
echo ""

# ── Verificar Python ──────────────────────────────────────────
echo "  [1/3] Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "  ERROR: Python 3 no encontrado."
    echo "  Descargalo en: https://python.org/downloads"
    echo ""
    exit 1
fi

PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    echo ""
    echo "  ERROR: Necesitas Python 3.11 o superior."
    echo "  Version actual: $(python3 --version)"
    echo "  Descarga la ultima version en: https://python.org/downloads"
    echo ""
    exit 1
fi
echo "  OK — $(python3 --version)"

# ── Crear carpetas base ──────────────────────────────────────
echo "  [2/3] Preparando carpetas..."
mkdir -p knowledge
echo "  OK — Estructura lista"

# ── Preparar .env ────────────────────────────────────────────
echo "  [3/3] Preparando variables de entorno..."
if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
    echo "  OK — .env creado desde .env.example (todavia vacio, lo llenamos en el setup)"
else
    echo "  OK — .env ya existe, no se toca"
fi

echo ""
echo "==========================================================="
echo ""
echo "  Todo listo. Ahora abre tu asistente de codificacion con IA"
echo "  (por ejemplo, ejecuta 'devin' en esta carpeta) y pidele que"
echo "  arranque AgentKit, por ejemplo:"
echo ""
echo "    Quiero construir mi agente de WhatsApp, sigue CLAUDE.md"
echo ""
echo "  Tu asistente te guiara paso a paso para construir"
echo "  tu agente de WhatsApp personalizado con IA."
echo "  (Ver guia.md si vas a usar Devin en vez de Claude Code)"
echo ""
echo "  Vas a necesitar:"
echo "    - Una API key de Gemini, gratis (aistudio.google.com/apikey)"
echo "    - Una cuenta de Zernio      (zernio.com — plan free, sin tarjeta)"
echo "      o credenciales de Meta Cloud API si prefieres conectarte tu mismo"
echo ""
echo "==========================================================="
echo ""
