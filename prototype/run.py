"""Punto de entrada de desarrollo.

Uso:
    python run.py            # servidor de desarrollo en http://127.0.0.1:5000
    flask --app run.py run   # equivalente con la CLI de Flask

En producción (PythonAnywhere) se usa ``wsgi.py``.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app(os.environ.get("FLASK_CONFIG", "development"))

if __name__ == "__main__":
    app.run()
