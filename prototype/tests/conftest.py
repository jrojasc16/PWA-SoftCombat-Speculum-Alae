"""Fixtures de pytest: app en TestingConfig y cliente de pruebas.

TestingConfig usa SQLite en memoria (ver app/config.py). Las tablas se crean
por test (``db.create_all``) y se descartan al terminar, garantizando aislamiento.
"""

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture
def app():
    """Aplicación Flask en configuración de pruebas con BD en memoria."""
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """Cliente HTTP de pruebas (sin levantar servidor)."""
    return app.test_client()
