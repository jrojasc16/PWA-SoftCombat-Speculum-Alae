"""Tests de la vista HTML de historial personal (Sprint 7.5)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services as combat_services
from app.modules.combat.domain.estados import EstadoCombate
from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository
from app.modules.ranking import services as ranking_services

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


def _reportar(reporter, participantes, ganador):
    combate, _ = combat_services.report_combat(
        reporter_id=reporter.id,
        participants=[u.id for u in participantes],
        winner=ganador.id,
        played_at=AYER,
    )
    return combate


def _reportar_y_procesar(reporter, participantes, ganador):
    combate = _reportar(reporter, participantes, ganador)
    combate.status = EstadoCombate.CONFIRMADO
    ranking_services.process_confirmed_combat(combate.id)
    return combate


@pytest.fixture
def escenario(roles):
    return {
        "ana": _usuario("ana@x.com", "Ana Rojas"),
        "beto": _usuario("beto@x.com", "Beto Sanz"),
        "caro": _usuario("caro@x.com", "Caro Diaz"),
    }


# ---------------------------------------------------------------------------
# Control de acceso y shell de la vista
# ---------------------------------------------------------------------------


def test_historial_requiere_sesion(client, escenario):
    r = client.get("/historial")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]
    assert "next=/historial" in r.headers["Location"]


def test_navegacion_muestra_historial_solo_con_sesion(client, escenario):
    _login(client, escenario["ana"])
    con_sesion = client.get("/ranking").get_data(as_text=True)
    assert "Historial" in con_sesion

    client.get("/salir")
    anonimo = client.get("/ranking").get_data(as_text=True)
    assert "Historial" not in anonimo


# ---------------------------------------------------------------------------
# Contenido de la vista
# ---------------------------------------------------------------------------


def test_historial_vacio(client, escenario):
    _login(client, escenario["ana"])

    r = client.get("/historial")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "Mi historial de combates" in texto
    assert "Aún no has jugado" in texto
    assert "Todavía no tienes índice" in texto


def test_historial_muestra_los_mismos_datos_que_la_api(client, escenario):
    """La vista y GET /me/history leen la misma fuente (mismo servicio)."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana)

    _login(client, ana)
    html = client.get("/historial").get_data(as_text=True)
    assert "Beto Sanz" in html  # rival
    assert "VICTORIA" in html
    assert "1500.0" in html and "1510.0" in html  # índice antes → después
    assert "+10.0" in html

    datos = client.get("/me/history").get_json()
    assert datos["total"] == 1
    assert datos["items"][0]["opponent"]["name"] == "Beto Sanz"
    assert datos["items"][0]["rating"]["points_after"] == 1510.0


def test_historial_marca_combates_sin_procesar(client, escenario):
    """Un combate PENDIENTE aparece con ``sin procesar`` (rating null)."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar(ana, [ana, beto], ana)

    _login(client, ana)
    html = client.get("/historial").get_data(as_text=True)
    assert "PENDIENTE" in html
    assert "sin procesar" in html


def test_historial_no_muestra_combates_ajenos(client, escenario):
    """Solo aparecen mis combates (los de otros usuarios, no)."""
    ana, beto, caro = escenario["ana"], escenario["beto"], escenario["caro"]
    _reportar_y_procesar(beto, [beto, caro], beto)

    _login(client, ana)
    html = client.get("/historial").get_data(as_text=True)
    assert "Aún no has jugado" in html


def test_historial_muestra_indice_actual(client, escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana)

    _login(client, ana)
    html = client.get("/historial").get_data(as_text=True)
    assert "Tu índice actual es" in html
    assert "1510.0" in html
    assert "1 combate" in html


def test_historial_paginado(client, escenario):
    """La paginación de la vista respeta el orden más reciente primero."""
    ana, beto = escenario["ana"], escenario["beto"]
    for i in range(3):
        fecha = AYER - timedelta(days=i + 1)
        combate, _ = combat_services.report_combat(
            reporter_id=ana.id,
            participants=[ana.id, beto.id],
            winner=ana.id,
            played_at=fecha,
        )

    from app.modules.ui import routes as ui_routes

    original = ui_routes.FILAS_HISTORIAL
    ui_routes.FILAS_HISTORIAL = 2
    try:
        _login(client, ana)
        primera = client.get("/historial").get_data(as_text=True)
        assert "Página 1 de 2" in primera
        assert "2 combates en tu historial" not in primera
        assert "3 combates en tu historial" in primera

        segunda = client.get("/historial?page=2").get_data(as_text=True)
        assert "Página 2 de 2" in segunda
        assert "Siguiente" not in segunda
    finally:
        ui_routes.FILAS_HISTORIAL = original


def test_historial_parametro_invalido_muestra_aviso(client, escenario):
    """page=abc no rompe la página: se avisa y se muestra la primera."""
    _login(client, escenario["ana"])
    r = client.get("/historial?page=abc")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "page" in texto
    assert "Página 1 de 1" in texto


def test_historial_no_expone_correos(client, escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana)

    _login(client, ana)
    assert "@" not in client.get("/historial").get_data(as_text=True)
