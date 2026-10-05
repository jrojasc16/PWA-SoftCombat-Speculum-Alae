"""Punto de entrada WSGI para producción (PythonAnywhere → tarea 14.2).

En el panel de PythonAnywhere se apunta el archivo WSGI a este módulo; la
variable de entorno ``FLASK_CONFIG=production`` se documenta en la guía de
despliegue (Sprint 13.2).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

application = create_app(os.environ.get("FLASK_CONFIG", "production"))
