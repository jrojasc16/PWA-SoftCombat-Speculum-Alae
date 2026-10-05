#!/usr/bin/env bash
# Chequeo local del proyecto: instala dependencias y corre pytest con cobertura.
# Falla si la cobertura del módulo de ranking baja del 70 % (RNF007).
# Uso: ./scripts/check.sh
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
echo "Chequeo OK."
