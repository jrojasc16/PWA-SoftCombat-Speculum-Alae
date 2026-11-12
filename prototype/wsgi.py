"""Punto de entrada WSGI para producción (PythonAnywhere → tarea 14.2).

En el panel de PythonAnywhere se apunta el archivo WSGI del sistema a este
módulo; las variables de entorno (``FLASK_CONFIG``, ``SECRET_KEY``,
``DATABASE_URL``) se cargan desde ``prototype/.env`` con python-dotenv —
la forma recomendada por PythonAnywhere para configuración sensible y que
evita duplicar valores entre consolas y el servidor web (guía de despliegue:
``documentation/DEPLOY_PYTHONANYWHERE.md``, Sprint 13.2).

``load_dotenv`` no pisa variables ya presentes en el entorno: si la
plataforma (o el operador) definió una variable, esa tiene prioridad sobre
el archivo.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Carga prototype/.env (no versionado) antes de leer la configuración.
load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402  (tras sys.path y load_dotenv)

application = create_app(os.environ.get("FLASK_CONFIG", "production"))
