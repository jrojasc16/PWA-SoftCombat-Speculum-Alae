"""Tests de la vista HTML de ranking público (Sprint 7.3)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services as combat_services
from app.modules.combat.domain.estados import EstadoCombate
from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository
from app.modules.ranking import services as ranking_services
from app.modules.ranking.models import Rating
from app.modules.ranking.repositories import RatingRepository

AYER = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)


def _usuario(email, nombre, rol="jugador", comunidad=1):
    user = iam_services.register_user(
        email=email, password="password123", name=nombre, community_id=comunidad
    )
    user.role_id = RoleRepository.get_by_name(rol).id
    db.session.commit()
    return user


def _reportar_y_procesar(reporter, participantes, ganador):
    combate, _ = combat_services.report_combat(
        reporter_id=reporter.id,
        participants=[u.id for u in participantes],
        winner=ganador.id,
        played_at=AYER,
    )
    combate.status = EstadoCombate.CONFIRMADO
    ranking_services.process_confirmed_combat(combate.id)
    return combate


@pytest.fixture
def escenario(roles):
    return {
        "ana": _usuario("ana@x.com", "Ana Rojas"),
        "beto": _usuario("beto@x.com", "Beto Sanz"),
    }


def test_ranking_es_publico(client, roles):
    """La vista no exige sesión (RF11)."""
    r = client.get("/ranking")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "Ranking de la comunidad" in texto
    assert "Todavía no hay combates" in texto


def test_ranking_muestra_los_mismos_datos_que_la_api(client, escenario):
    """La tabla y GET /api/ranking leen la misma fuente (misma caché y TTL)."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana)

    html = client.get("/ranking").get_data(as_text=True)
    assert "Ana Rojas" in html
    assert "Beto Sanz" in html
    assert "1510.0" in html
    assert "1490.0" in html

    items = client.get("/api/ranking").get_json()["items"]
    assert [i["name"] for i in items] == ["Ana Rojas", "Beto Sanz"]


def test_ranking_no_expone_correos(client, escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana)

    assert "@" not in client.get("/ranking").get_data(as_text=True)


def test_ranking_paginado(client, escenario):
    """La paginación de la vista respeta el orden global de posiciones."""
    for i in range(3):
        usuario = _usuario(f"j{i}@x.com", f"Jugador {i}")
        RatingRepository.add(
            Rating(user_id=usuario.id, community_id=1, points=1500.0 - i * 10)
        )
    RatingRepository.save()

    # FILAS_RANKING = 25 por defecto; se fuerza una página pequeña con la BD.
    from app.modules.ui import routes as ui_routes

    original = ui_routes.FILAS_RANKING
    ui_routes.FILAS_RANKING = 2
    try:
        primera = client.get("/ranking").get_data(as_text=True)
        assert "Jugador 0" in primera and "Jugador 1" in primera
        assert "Jugador 2" not in primera
        assert "Página 1 de 2" in primera

        segunda = client.get("/ranking?page=2").get_data(as_text=True)
        assert "Jugador 2" in segunda
        assert "Página 2 de 2" in segunda
        assert "Siguiente" not in segunda
    finally:
        ui_routes.FILAS_RANKING = original


def test_ranking_parametro_invalido_muestra_aviso(client, escenario):
    """page=abc no rompe la página: se avisa y se muestra la primera."""
    r = client.get("/ranking?page=abc")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "page" in texto
    assert "Página 1 de 1" in texto


def test_ranking_aisla_por_comunidad(client, escenario, roles):
    """RNF006: el ranking de otra comunidad no mezcla jugadores."""
    ana, beto = escenario["ana"], escenario["beto"]
    _reportar_y_procesar(ana, [ana, beto], ana)
    _usuario("otro@x.com", "Otro Jugador", comunidad=2)

    html = client.get("/ranking").get_data(as_text=True)
    assert "Ana Rojas" in html and "Otro Jugador" not in html

    html2 = client.get("/ranking?community_id=2").get_data(as_text=True)
    assert "Ana Rojas" not in html2
