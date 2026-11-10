"""Tests del envío offline con cola IndexedDB (Sprint 9).

Son pruebas de contrato sobre los estáticos del cliente (el navegador no está
disponible en el entorno de ejecución) más las pruebas del servidor que
garantizan la idempotencia de los reenvíos (``client_request_id``).
"""

import json
import re

import pytest

from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository
from app.extensions import db


def _usuario(email, nombre, rol="jugador", comunidad=1):
    user = iam_services.register_user(
        email=email, password="password123", name=nombre, community_id=comunidad
    )
    user.role_id = RoleRepository.get_by_name(rol).id
    db.session.commit()
    return user


@pytest.fixture
def jugador(roles):
    return _usuario("ana@x.com", "Ana Rojas")


def _login(client, usuario):
    r = client.post(
        "/auth/login", json={"email": usuario.email, "password": "password123"}
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 9.1 — db.js: wrapper de IndexedDB con store outbox (FIFO)
# ---------------------------------------------------------------------------


def test_db_js_se_sirve_como_javascript(client):
    r = client.get("/static/db.js")
    assert r.status_code == 200
    assert "javascript" in r.content_type
    assert "SAOutbox" in r.get_data(as_text=True)


def test_db_js_usa_indexeddb_con_el_store_outbox(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    assert "indexedDB.open" in js
    assert 'NOMBRE_BD = "speculum-alae"' in js
    assert 'STORE_OUTBOX = "outbox"' in js


def test_db_js_garantiza_el_orden_fifo_de_la_cola(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    # Clave autoincremental: el orden de la cola es el de inserción.
    assert "autoIncrement: true" in js
    assert "a.id || 0) - (b.id || 0)" in js


def test_db_js_guarda_clave_de_idempotencia_y_estado(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    assert "client_request_id" in js
    assert 'createIndex("client_request_id"' in js
    assert "intentos" in js
    assert "last_error" in js
    assert "created_at" in js


def test_db_js_expone_la_api_de_la_cola(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    for funcion in (
        "encolar",
        "listar",
        "actualizar",
        "eliminar",
        "contarPendientes",
    ):
        assert funcion in js


def test_db_js_avisa_si_el_navegador_no_soporta_indexeddb(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    assert "no soporta IndexedDB" in js
    assert "disponible" in js


def test_db_js_guarda_el_directorio_para_poder_reportar_sin_conexion(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    assert 'STORE_DIRECTORIO = "directorio"' in js
    assert "guardarDirectorio" in js
    assert "leerDirectorio" in js
