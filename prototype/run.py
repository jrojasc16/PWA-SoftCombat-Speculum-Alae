"""Punto de entrada de desarrollo.

Uso:
    python run.py            # servidor de desarrollo en http://127.0.0.1:5000
    flask --app run.py run   # equivalente con la CLI de Flask

En producción (PythonAnywhere) se usa ``wsgi.py``. Ambos cargan el archivo
opcional ``prototype/.env`` con python-dotenv (variables de entorno sin
versionar; ver ``documentation/DEPLOY_PYTHONANYWHERE.md``).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Carga prototype/.env si existe (no pisa variables ya definidas).
load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402  (tras sys.path y load_dotenv)

app = create_app(os.environ.get("FLASK_CONFIG", "development"))

if __name__ == "__main__":
    app.run()
