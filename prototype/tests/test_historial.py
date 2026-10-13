"""Tests del endpoint de historial GET /me/history (Sprint 7.1)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services as combat_services
from app.modules.combat.domain.estados import EstadoCombate
from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository
from app.modules.ranking import services as ranking_services

AYER = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
AYER_MAS = AYER - timedelta(days=7)


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


def _reportar(reporter, participantes, ganador, jugado=AYER, **extra):
    combate, _ = combat_services.report_combat(
        reporter_id=reporter.id,
        participants=[u.id for u in participantes],
        winner=ganador.id,
        played_at=jugado,
        **extra,
    )
    return combate


def _reportar_y_procesar(reporter, participantes, ganador, jugado=AYER, **extra):
    """Reporta un combate, lo cierra en CONFIRMADO y dispara el recálculo on-write."""
    combate = _reportar(reporter, participantes, ganador, jugado=jugado, **extra)
    combate.status = EstadoCombate.CONFIRMADO
    ranking_services.process_confirmed_combat(combate.id)
    return combate


@pytest.fixture
def escenario(roles):
    return {
        "ana": _usuario("ana@x.com", "Ana Rojas"),
        "beto": _usuario("beto@x.com", "Beto Sanz"),
    }


# ---------------------------------------------------------------------------
# 7.1 — contrato del endpoint
# ---------------------------------------------------------------------------


def test_historial_requiere_sesion(client, escenario):
    """Sin sesión el endpoint responde 401 JSON (nunca redirige)."""
    r = client.get("/me/history")
    assert r.status_code == 401
    assert r.get_json() == {"error": "Autenticación requerida."}


def test_historial_sin_combates(client, escenario):
    """Un jugador nuevo ve un historial vacío y sin índice todavía."""
    _login(client, escenario["ana"])

    cuerpo = client.get("/me/history").get_json()
    assert cuerpo["total"] == 0
    assert cuerpo["items"] == []
    assert cuerpo["rating"] is None
    assert cuerpo["page"] == 1
    assert cuerpo["per_page"] == 50


def test_historial_incluye_resultado_rival_y_rating(client, escenario):
    """El item trae rival, resultado y la variación de índice del combate."""
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar_y_procesar(ana, [ana, beto], ana)
    _login(client, ana)

    cuerpo = client.get("/me/history").get_json()
    assert cuerpo["total"] == 1
    assert cuerpo["rating"] == {"points": pytest.approx(1510.0), "matches_played": 1}

    item = cuerpo["items"][0]
    assert item["combat_id"] == combate.id
    assert item["status"] == "CONFIRMADO"
    assert item["opponent"] == {"id": beto.id, "name": "Beto Sanz"}
    assert item["result"] == "VICTORIA"
    assert item["winner_id"] == ana.id
    assert item["rating"]["points_before"] == pytest.approx(1500.0)
    assert item["rating"]["points_after"] == pytest.approx(1510.0)
    assert item["rating"]["delta"] == pytest.approx(10.0)
    assert item["rating"]["matches_played"] == 1


def test_historial_refleja_la_derrota_del_jugador(client, escenario):
    """El mismo combate se lee distinto desde cada participante."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana)
    _login(client, beto)

    item = client.get("/me/history").get_json()["items"][0]
    assert item["result"] == "DERROTA"
    assert item["opponent"] == {"id": ana.id, "name": "Ana Rojas"}
    assert item["rating"]["points_after"] == pytest.approx(1490.0)
    assert item["rating"]["delta"] == pytest.approx(-10.0)


def test_historial_combate_no_procesado_sin_rating(client, escenario):
    """Un combate PENDIENTE no tiene snapshot de RatingHistory (rating: null)."""
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    _login(client, ana)

    item = client.get("/me/history").get_json()["items"][0]
    assert item["combat_id"] == combate.id
    assert item["status"] == "PENDIENTE"
    assert item["result"] == "VICTORIA"
    assert item["rating"] is None


def test_historial_combate_en_conflicto(client, escenario):
    """Los combates en CONFLICTO también aparecen, aún sin resolver."""
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    combate.status = EstadoCombate.CONFLICTO
    db.session.commit()
    _login(client, ana)

    item = client.get("/me/history").get_json()["items"][0]
    assert item["combat_id"] == combate.id
    assert item["status"] == "CONFLICTO"
    assert item["rating"] is None


def test_historial_solo_incluye_los_combates_del_usuario(client, escenario):
    """Nunca se filtran combates ajenos ni se expone la partida de otro."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana)
    _login(client, beto)

    cuerpo = client.get("/me/history").get_json()
    assert cuerpo["total"] == 1
    assert [i["opponent"]["name"] for i in cuerpo["items"]] == ["Ana Rojas"]


def test_historial_orden_mas_reciente_primero(client, escenario):
    """El orden es de más reciente a más antiguo (juego, no inserción)."""
    ana, beto = escenario["ana"], escenario["beto"]
    viejo = _reportar_y_procesar(ana, [ana, beto], ana, jugado=AYER_MAS)
    nuevo = _reportar_y_procesar(ana, [ana, beto], beto, jugado=AYER)
    _login(client, ana)

    items = client.get("/me/history").get_json()["items"]
    assert [i["combat_id"] for i in items] == [nuevo.id, viejo.id]
    assert [i["result"] for i in items] == ["DERROTA", "VICTORIA"]


def test_historial_paginado(client, escenario):
    """La paginación recorta la página pero mantiene el total."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana, jugado=AYER_MAS)
    _reportar_y_procesar(ana, [ana, beto], beto, jugado=AYER)
    _login(client, ana)

    primera = client.get("/me/history?page=1&per_page=1").get_json()
    assert primera["total"] == 2
    assert primera["page"] == 1
    assert len(primera["items"]) == 1
    assert primera["items"][0]["result"] == "DERROTA"  # la más reciente

    segunda = client.get("/me/history?page=2&per_page=1").get_json()
    assert len(segunda["items"]) == 1
    assert segunda["items"][0]["result"] == "VICTORIA"


def test_historial_parametros_invalidos(client, escenario):
    """Los parámetros de página fuera de rango responden 400 con su campo."""
    _login(client, escenario["ana"])

    for query in ("page=0", "page=abc", "per_page=0", "per_page=1000"):
        r = client.get(f"/me/history?{query}")
        assert r.status_code == 400
        assert "page" in r.get_json()["error"] or "per_page" in r.get_json()["error"]


def test_historial_no_expone_correos(client, escenario):
    """El DTO del historial jamás publica correos ni credenciales."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana)
    _login(client, ana)

    texto = client.get("/me/history").get_data(as_text=True)
    assert "@" not in texto
    assert "password" not in texto
    assert "password_hash" not in texto
