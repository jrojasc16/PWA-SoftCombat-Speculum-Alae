#!/usr/bin/env bash
# Chequeo local del proyecto: instala dependencias y corre pytest con cobertura.
# Falla si la cobertura del módulo de ranking baja del 70 % (RNF007).
#
# Uso:
#   ./scripts/check.sh                 # solo tests y cobertura
#   ./scripts/check.sh --con-navegador  # además verifica la cola offline y el
#                                       # panel de administración en un
#                                       # navegador real (requiere la app en
#                                       # marcha en http://127.0.0.1:5000)
set -euo pipefail

cd "$(dirname "$0")/.."          # raíz del repo
PY="$PWD/venv/bin/python"        # ruta absoluta (el cwd cambia a prototype/)

if [ ! -x "$PY" ]; then
  echo "No existe el entorno virtual: crea venv/ e instala requirements."
  echo "  python3 -m venv venv && venv/bin/pip install -r prototype/requirements.txt"
  exit 1
fi

cd prototype
"$PY" -m pytest --cov=app.modules.ranking --cov-fail-under=70 --cov-report=term-missing
cd ..

if [ "${1:-}" = "--con-navegador" ]; then
  echo "Verificando la cola offline en un navegador real..."
  "$PY" scripts/verificar_offline_browser.py --url "${2:-http://127.0.0.1:5000}"
  echo "Verificando el panel de administración en un navegador real..."
  "$PY" scripts/verificar_admin_browser.py --url "${2:-http://127.0.0.1:5000}"
fi

echo "Chequeo OK."
