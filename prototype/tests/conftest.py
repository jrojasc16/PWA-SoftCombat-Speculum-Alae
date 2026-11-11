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


@pytest.fixture(autouse=True)
def _usuario_fresco_por_peticion(app):
    """Invalida la caché de Flask-Login entre peticiones (Sprint 12.3).

    Flask-Login memoriza ``current_user`` en ``g._login_user`` y solo lo
    recarga si la variable no existe. Como el fixture ``app`` mantiene un
    único app context abierto durante todo el test, ``g`` se comparte entre
    peticiones y entre clientes: sin esta limpieza, la petición de un cliente
    reutilizaría el usuario que otro cliente dejó en caché en lugar de leer
    su propia cookie de sesión. En producción cada petición recibe su propio
    app context (y por tanto su propia ``g``); este hook reproduce ese
    comportamiento para que las pruebas multi-sesión vean lo mismo que el
    servidor real.
    """
    from flask import g

    @app.before_request
    def _limpiar_usuario_en_cache():
        g.pop("_login_user", None)


@pytest.fixture
def roles(app):
    """Siembra los 4 roles fijos en la BD de pruebas (equivale a la migración de datos).

    Devuelve un dict nombre → Role para asignar role_id en los tests.
    """
    from app.modules.iam.models import Role

    creados = {}
    for nombre in ("jugador", "arbitro", "admin", "super_admin"):
        rol = Role(name=nombre)
        _db.session.add(rol)
        creados[nombre] = rol
    _db.session.commit()
    return creados

