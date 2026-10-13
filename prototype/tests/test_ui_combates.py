"""Tests de las vistas de combate del Sprint 7.4 (/reportar y /pendientes).

Las páginas son shells de HTML: la lógica de envío vive en la API JSON
(``POST /combats`` y ``POST /combats/<id>/confirm``), así que aquí se cubre
el shell, el control de acceso y el directorio que alimenta los formularios.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services as combat_services
from app.modules.iam import services as iam_services
from app.modules.iam.models import User
from app.modules.iam.repositories import RoleRepository, UserRepository

AYER = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)


def _usuario(email, nombre, rol="jugador", comunidad=1):
    user = iam_services.register_user(
        email=email, password="password123", name=nombre, community_id=comunidad
    )
    user.role_id = RoleRepository.get_by_name(rol).id
    db.session.commit()
    return user


def _login(client, usuario):
    r = client.post(
        "/auth/login", json={"email": usuario.email, "password": "password123"}
    )
    assert r.status_code == 200


@pytest.fixture
def escenario(roles):
    return {
        "ana": _usuario("ana@x.com", "Ana Rojas"),
        "beto": _usuario("beto@x.com", "Beto Sanz"),
        "caro": _usuario("caro@x.com", "Caro Diaz", rol="arbitro"),
        "dona": _usuario("dona@x.com", "Dona Eva", rol="admin"),
    }


# ---------------------------------------------------------------------------
# Control de acceso y shell de las vistas
# ---------------------------------------------------------------------------


def test_reportar_requiere_sesion(client, escenario):
    r = client.get("/reportar")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]
    assert "next=/reportar" in r.headers["Location"]


def test_pendientes_requiere_sesion(client, escenario):
    r = client.get("/pendientes")
    assert r.status_code == 302
    assert "next=/pendientes" in r.headers["Location"]


def test_pagina_reportar(client, escenario):
    _login(client, escenario["ana"])

    r = client.get("/reportar")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert 'id="form-reporte"' in texto
    assert 'id="lista-jugadores"' in texto
    assert 'id="lista-arbitros"' in texto
    assert 'name="jugado"' in texto
    assert "Árbitro (opcional)" in texto


def test_pagina_pendientes(client, escenario):
    _login(client, escenario["ana"])

    r = client.get("/pendientes")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert 'id="lista-pendientes"' in texto
    assert "Confirmaciones pendientes" in texto


def test_navegacion_muestra_reportar_y_pendientes(client, escenario):
    """La barra de navegación solo ofrece las acciones con sesión iniciada."""
    _login(client, escenario["ana"])

    con_sesion = client.get("/ranking").get_data(as_text=True)
    assert "Reportar" in con_sesion
    assert "Pendientes" in con_sesion

    client.get("/salir")
    anonimo = client.get("/ranking").get_data(as_text=True)
    assert "Reportar" not in anonimo
    assert "Pendientes" not in anonimo


# ---------------------------------------------------------------------------
# Directorio de la comunidad (alimenta los datalists del formulario)
# ---------------------------------------------------------------------------


def test_directorio_requiere_sesion(client, escenario):
    r = client.get("/me/community")
    assert r.status_code == 401
    assert r.get_json() == {"error": "Autenticación requerida."}


def test_directorio_publica_solo_id_nombre_y_rol(client, escenario):
    """El directorio resuelve nombre → id sin filtrar correos (RNF de datos)."""
    _login(client, escenario["ana"])

    r = client.get("/me/community")
    assert r.status_code == 200
    cuerpo = r.get_json()
    assert cuerpo["community_id"] == 1
    assert cuerpo["yo"] == {"id": escenario["ana"].id, "name": "Ana Rojas"}
    assert {j["name"] for j in cuerpo["jugadores"]} == {
        "Beto Sanz",
        "Caro Diaz",
        "Dona Eva",
    }
    # Árbitros: quien tiene rol de árbitro o de administración.
    assert {a["name"] for a in cuerpo["arbitros"]} == {"Caro Diaz", "Dona Eva"}
    assert "@" not in r.get_data(as_text=True)
    assert "password" not in r.get_data(as_text=True)


def test_directorio_aisla_por_comunidad(client, escenario):
    """RNF006: no aparecen jugadores de otra comunidad."""
    _usuario("otro@x.com", "Otro Jugador", comunidad=2)
    _login(client, escenario["ana"])

    jugadores = client.get("/me/community").get_json()["jugadores"]
    assert "Otro Jugador" not in {j["name"] for j in jugadores}


def test_directorio_excluye_usuarios_desactivados(client, escenario):
    beto = escenario["beto"]
    beto.active = False
    db.session.commit()

    _login(client, escenario["ana"])
    jugadores = client.get("/me/community").get_json()["jugadores"]
    assert "Beto Sanz" not in {j["name"] for j in jugadores}


# ---------------------------------------------------------------------------
# Flujo completo que usan las páginas (reporte → pendiente → confirmación)
# ---------------------------------------------------------------------------


def test_flujo_reportar_y_confirmar_que_usan_las_paginas(client, escenario):
    """Ana reporta con el contrato del formulario y ambos participantes confirman.

    El reporte no cuenta como confirmación (Sprint 5): el combate cierra en
    ``CONFIRMADO`` cuando los dos participantes declaran el mismo ganador.
    """
    ana, beto = escenario["ana"], escenario["beto"]
    _login(client, ana)

    # El formulario envía participants, winner y played_at (y referee_id opcional).
    r = client.post(
        "/combats",
        json={
            "participants": [ana.id, beto.id],
            "winner": ana.id,
            "played_at": AYER.isoformat(),
        },
    )
    assert r.status_code == 201
    combate_id = r.get_json()["id"]
    assert r.get_json()["status"] == "PENDIENTE"

    # Beto lo ve en su página de pendientes y confirma el mismo ganador.
    client.get("/salir")
    _login(client, beto)
    pendientes = client.get("/combats/pending").get_json()
    assert [c["id"] for c in pendientes] == [combate_id]

    r = client.post(f"/combats/{combate_id}/confirm", json={"winner_id": ana.id})
    assert r.status_code == 200
    # Con una sola confirmación (de las dos requeridas) sigue PENDIENTE.
    assert r.get_json()["status"] == "PENDIENTE"

    # Ana confirma lo mismo que reportó y el combate cierra en CONFIRMADO.
    client.get("/salir")
    _login(client, ana)
    r = client.post(f"/combats/{combate_id}/confirm", json={"winner_id": ana.id})
    assert r.status_code == 200
    assert r.get_json()["status"] == "CONFIRMADO"


def test_conflicto_sale_de_la_cola_de_pendientes(client, escenario):
    """Un combate en CONFLICTO deja de pedir confirmación a los jugadores.

    Su resolución corresponde al administrador (``GET /admin/combats?status=
    CONFLICTO``, panel del Sprint 10), no a la cola de pendientes.
    """
    ana, beto = escenario["ana"], escenario["beto"]
    combate, _ = combat_services.report_combat(
        reporter_id=ana.id,
        participants=[ana.id, beto.id],
        winner=ana.id,
        played_at=AYER,
    )
    combat_services.confirm_combat(
        user_id=ana.id, combat_id=combate.id, result={"winner_id": ana.id}
    )
    combat_services.confirm_combat(
        user_id=beto.id, combat_id=combate.id, result={"winner_id": beto.id}
    )
    assert combate.status.value == "CONFLICTO"

    _login(client, ana)
    assert client.get("/combats/pending").get_json() == []


def test_directorio_refleja_el_rol_asignado(client, escenario, roles):
    """El rol se cambia en la BD y el directorio lo refleja sin reloguear."""
    beto = UserRepository.get_by_id(escenario["beto"].id)
    beto.role_id = roles["arbitro"].id
    db.session.commit()

    _login(client, escenario["ana"])
    arbitros = client.get("/me/community").get_json()["arbitros"]
    assert {"id": beto.id, "name": "Beto Sanz"} in arbitros
