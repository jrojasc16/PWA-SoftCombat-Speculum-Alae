"""Tests del endpoint público GET /api/ranking (Sprint 6.5 y 6.6)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services as combat_services
from app.modules.combat.domain.estados import EstadoCombate
from app.modules.public_api import services as public_services
from app.modules.ranking import services as ranking_services
from app.modules.ranking.models import Rating
from app.modules.ranking.repositories import RatingRepository
from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository

AYER = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)


def _usuario(email, nombre, rol="jugador", comunidad=1):
    user = iam_services.register_user(
        email=email, password="password123", name=nombre, community_id=comunidad
    )
    user.role_id = RoleRepository.get_by_name(rol).id
    db.session.commit()
    return user


@pytest.fixture
def escenario(roles):
    return {
        "ana": _usuario("ana@x.com", "Ana Rojas"),
        "beto": _usuario("beto@x.com", "Beto Sanz"),
        "caro": _usuario("caro@x.com", "Caro Diaz", rol="arbitro"),
        "dona": _usuario("dona@x.com", "Dona Eva", rol="admin"),
    }


def _reportar_y_cerrar(reporter, participantes, ganador, **extra):
    combate, _ = combat_services.report_combat(
        reporter_id=reporter.id,
        participants=[u.id for u in participantes],
        winner=ganador.id,
        played_at=AYER,
        **extra,
    )
    combate.status = EstadoCombate.CONFIRMADO
    ranking_services.process_confirmed_combat(combate.id)
    return combate


# ---------------------------------------------------------------------------
# 6.5 — contrato del endpoint
# ---------------------------------------------------------------------------


def test_api_ranking_publica_sin_sesion(client, escenario):
    """El endpoint no exige autenticación (RF11 / RNF004)."""
    r = client.get("/api/ranking")
    assert r.status_code == 200
    cuerpo = r.get_json()
    assert cuerpo["total"] == 0
    assert cuerpo["items"] == []
    assert r.headers["Cache-Control"].startswith("public, max-age=")


def test_api_ranking_sin_datos_sensibles(client, escenario):
    """El DTO expone solo position/name/points/matches_played."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_cerrar(ana, [ana, beto], ana)

    r = client.get("/api/ranking")
    items = r.get_json()["items"]
    assert items == [
        {
            "position": 1,
            "name": "Ana Rojas",
            "points": pytest.approx(1510.0),
            "matches_played": 1,
        },
        {
            "position": 2,
            "name": "Beto Sanz",
            "points": pytest.approx(1490.0),
            "matches_played": 1,
        },
    ]
    texto = r.get_data(as_text=True)
    assert "@" not in texto  # nunca correos
    assert "password" not in texto


def test_api_ranking_ordenado_por_puntos_desc(client, escenario):
    ana, beto, caro = escenario["ana"], escenario["beto"], escenario["caro"]
    _reportar_y_cerrar(ana, [ana, beto], ana)
    _reportar_y_cerrar(ana, [ana, beto], ana)

    items = client.get("/api/ranking").get_json()["items"]
    puntos = [i["points"] for i in items]
    assert puntos == sorted(puntos, reverse=True)
    assert [i["position"] for i in items] == [1, 2]


def test_api_ranking_paginado(client, escenario):
    for i in range(3):
        usuario = _usuario(f"j{i}@x.com", f"Jugador {i}")
        RatingRepository.add(
            Rating(user_id=usuario.id, community_id=1, points=1500.0 - i * 10)
        )
    RatingRepository.save()

    primera = client.get("/api/ranking?page=1&per_page=2").get_json()
    assert primera["total"] == 3
    assert len(primera["items"]) == 2
    assert primera["items"][0]["position"] == 1

    segunda = client.get("/api/ranking?page=2&per_page=2").get_json()
    assert len(segunda["items"]) == 1
    # La posición es global: continúa en 3, no vuelve a 1.
    assert segunda["items"][0]["position"] == 3

    assert db.session.query(Rating).count() == 3


@pytest.mark.parametrize(
    "query, mensaje",
    [
        ("page=0", "page"),
        ("per_page=0", "per_page"),
        ("per_page=1000", "per_page"),
        ("page=abc", "page"),
        ("community_id=x", "community_id"),
    ],
)
def test_api_ranking_parametros_invalidos(client, escenario, query, mensaje):
    r = client.get(f"/api/ranking?{query}")
    assert r.status_code == 400
    assert mensaje in r.get_json()["error"]


# ---------------------------------------------------------------------------
# Caché e invalidación
# ---------------------------------------------------------------------------


def _con_ttl(app, segundos, prueba):
    """Ejecuta una prueba con ``RANKING_CACHE_TTL`` activo y limpia al salir."""
    app.config["RANKING_CACHE_TTL"] = segundos
    public_services.invalidar_cache()
    try:
        return prueba()
    finally:
        app.config["RANKING_CACHE_TTL"] = 0
        public_services.invalidar_cache()


def test_cache_guarda_el_resultado_y_se_invalida(app, escenario):
    """La caché sirve el payload guardado hasta que algo la invalida (RNF004)."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_cerrar(ana, [ana, beto], ana)

    def prueba():
        primero = public_services.ranking_publico(1, 1, 50)
        assert primero["items"][0]["name"] == "Ana Rojas"
        assert primero["items"][0]["points"] == pytest.approx(1510.0)

        # Cambio directo en la BD sin pasar por los servicios: la caché lo oculta.
        rating = RatingRepository.get(ana.id, 1)
        rating.points = 1000.0
        RatingRepository.save()
        assert public_services.ranking_publico(1, 1, 50) is primero

        # Tras invalidar (lo que hace el hook de cada recálculo) se ve lo nuevo.
        public_services.invalidar_cache()
        tercero = public_services.ranking_publico(1, 1, 50)
        assert tercero is not primero
        assert tercero["items"][0]["name"] == "Beto Sanz"
        assert tercero["items"][0]["points"] == pytest.approx(1490.0)

    _con_ttl(app, 60, prueba)


def test_confirmar_invalida_cache_tras_el_recalculo(app, client, escenario):
    """Un segundo combate no puede quedar oculto por la caché del primero."""
    ana, beto = escenario["ana"], escenario["beto"]

    def prueba():
        _reportar_y_cerrar(ana, [ana, beto], ana)
        assert client.get("/api/ranking").get_json()["items"][0]["matches_played"] == 1

        _reportar_y_cerrar(ana, [ana, beto], ana)
        items = client.get("/api/ranking").get_json()["items"]
        assert items[0]["matches_played"] == 2
        assert items[0]["name"] == "Ana Rojas"

    _con_ttl(app, 60, prueba)


def test_recálculo_manual_invalida_cache(app, client, escenario):
    """POST /admin/ranking/recalculate reconstruye y deja la caché limpia."""
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]

    def prueba():
        _reportar_y_cerrar(ana, [ana, beto], ana)
        assert client.get("/api/ranking").get_json()["total"] == 2

        # Se corrompe el índice a mano y se vuelve a poblar la caché con ese
        # valor: ahora la caché está "sucia" a propósito.
        rating = RatingRepository.get(ana.id, 1)
        rating.points = 9999.0
        RatingRepository.save()
        public_services.invalidar_cache()
        items = client.get("/api/ranking").get_json()["items"]
        assert items[0]["points"] == pytest.approx(9999.0)

        client.post("/auth/login", json={"email": dona.email, "password": "password123"})
        r = client.post("/admin/ranking/recalculate")
        assert r.status_code == 200
        assert r.get_json()["combats_processed"] == 1

        # Si el recálculo no invalidara la caché, seguiríamos viendo 9999.
        items = client.get("/api/ranking").get_json()["items"]
        assert items[0]["points"] == pytest.approx(1510.0)
        assert items[0]["matches_played"] == 1
        assert RatingRepository.get(ana.id, 1).points == pytest.approx(1510.0)

    _con_ttl(app, 60, prueba)
