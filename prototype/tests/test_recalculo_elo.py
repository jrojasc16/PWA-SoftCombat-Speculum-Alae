"""Tests del recálculo on-write (Sprint 6.2, 6.3, 6.4 y 6.6)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services as combat_services
from app.modules.combat.domain.estados import EstadoCombate
from app.modules.ranking import services as ranking_services
from app.modules.ranking.domain.constants import RATING_INICIAL
from app.modules.ranking.models import Rating, RatingHistory
from app.modules.ranking.repositories import RatingHistoryRepository, RatingRepository
from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository
from app.shared.errors import DomainError, NotFoundError

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
    ana = _usuario("ana@x.com", "Ana Rojas")
    beto = _usuario("beto@x.com", "Beto Sanz")
    caro = _usuario("caro@x.com", "Caro Diaz", rol="arbitro")
    dona = _usuario("dona@x.com", "Dona Eva", rol="admin")
    return {"ana": ana, "beto": beto, "caro": caro, "dona": dona}


def _reportar(reporter, participantes, ganador, **extra):
    combate, _ = combat_services.report_combat(
        reporter_id=reporter.id,
        participants=[u.id for u in participantes],
        winner=ganador.id,
        played_at=AYER,
        **extra,
    )
    return combate


def _puntos(user_id, community_id=1):
    return RatingRepository.get(user_id, community_id)


# ---------------------------------------------------------------------------
# 6.2 — process_confirmed_combat
# ---------------------------------------------------------------------------


def test_primer_combate_usa_rating_inicial_y_tablas(escenario):
    """Ambos empiezan en 1500 con t=10 y x=2 → 1510 / 1490 (Art. 30)."""
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    combate.status = EstadoCombate.CONFIRMADO

    assert ranking_services.process_confirmed_combat(combate.id) is True

    assert _puntos(ana.id).points == pytest.approx(1510.0)
    assert _puntos(beto.id).points == pytest.approx(1490.0)
    assert _puntos(ana.id).matches_played == 1
    assert _puntos(beto.id).matches_played == 1
    assert combate.processed is True

    historial = RatingHistoryRepository.entradas_de_comunidad(1)
    assert len(historial) == 2
    assert {h.user_id for h in historial} == {ana.id, beto.id}
    assert {h.k for h in historial} == {20.0}
    assert {h.percentil for h in historial} == {0.0}


def test_idempotencia_no_reprocesa_ni_duplica(escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    combate.status = EstadoCombate.CONFIRMADO

    ranking_services.process_confirmed_combat(combate.id)
    puntos_ana = _puntos(ana.id).points

    assert ranking_services.process_confirmed_combat(combate.id) is False
    assert _puntos(ana.id).points == puntos_ana
    assert _puntos(ana.id).matches_played == 1
    assert len(RatingHistoryRepository.entradas_de_comunidad(1)) == 2


def test_combate_no_terminal_no_se_procesa(escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    with pytest.raises(DomainError, match="confirmados o resueltos"):
        ranking_services.process_confirmed_combat(combate.id)
    assert RatingRepository.get(ana.id, 1) is None
    assert combate.processed is False


def test_combate_inexistente(escenario):
    with pytest.raises(NotFoundError, match="combate"):
        ranking_services.process_confirmed_combat(4242)


def test_segundo_combate_usa_percentiles_distintos(escenario):
    """El líder pasa a percentil 100 → x=0.2 (k=2) frente a x=2 (k=20)."""
    ana, beto = escenario["ana"], escenario["beto"]
    primero = _reportar(ana, [ana, beto], ana)
    primero.status = EstadoCombate.CONFIRMADO
    ranking_services.process_confirmed_combat(primero.id)

    segundo = _reportar(ana, [ana, beto], ana)
    segundo.status = EstadoCombate.CONFIRMADO
    ranking_services.process_confirmed_combat(segundo.id)

    historial = [
        h for h in RatingHistoryRepository.entradas_de_comunidad(1)
        if h.combat_id == segundo.id
    ]
    por_usuario = {h.user_id: h for h in historial}
    assert por_usuario[ana.id].percentil == 100.0
    assert por_usuario[ana.id].k == pytest.approx(2.0)
    assert por_usuario[beto.id].percentil == 0.0
    assert por_usuario[beto.id].k == pytest.approx(20.0)
    assert _puntos(ana.id).matches_played == 2
    assert _puntos(beto.id).matches_played == 2


def test_atomicidad_revante_si_falla_a_mitad(escenario, monkeypatch):
    """Fallo a mitad del cálculo → rollback completo, sin estados parciales."""
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    combate.status = EstadoCombate.CONFIRMADO

    original = RatingHistoryRepository.add
    llamadas = {"n": 0}

    def _fallar_al_segundo(entry):
        llamadas["n"] += 1
        if llamadas["n"] >= 2:
            raise RuntimeError("fallo simulado a mitad del recálculo")
        return original(entry)

    monkeypatch.setattr(ranking_services.RatingHistoryRepository, "add", _fallar_al_segundo)

    with pytest.raises(RuntimeError, match="fallo simulado"):
        ranking_services.process_confirmed_combat(combate.id)

    assert db.session.query(Rating).count() == 0
    assert db.session.query(RatingHistory).count() == 0
    assert combate.processed is False


# ---------------------------------------------------------------------------
# 6.3 — hook: confirmar actualiza el ranking en la misma transacción
# ---------------------------------------------------------------------------


def test_confirmar_combate_actualiza_ranking(client, escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)

    r = client.post(
        "/auth/login", json={"email": ana.email, "password": "password123"}
    )
    assert r.status_code == 200

    client.post(f"/combats/{combate.id}/confirm", json={"winner_id": ana.id})
    assert _puntos(ana.id) is None  # un solo confirmante: sigue pendiente

    client.post("/auth/logout")
    r = client.post(
        "/auth/login", json={"email": beto.email, "password": "password123"}
    )
    assert r.status_code == 200

    r = client.post(f"/combats/{combate.id}/confirm", json={"winner_id": ana.id})
    assert r.status_code == 200
    assert r.get_json()["status"] == "CONFIRMADO"

    assert _puntos(ana.id).points == pytest.approx(1510.0)
    assert _puntos(beto.id).points == pytest.approx(1490.0)
    assert combate.processed is True


def test_conflicto_resuelto_por_admin_recalcula_todo(escenario):
    """La edición admin dispara el recálculo completo desde el historial."""
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate = _reportar(ana, [ana, beto], ana)
    combat_services.confirm_combat(ana.id, combate.id, ana.id)
    combat_services.confirm_combat(beto.id, combate.id, beto.id)
    assert combate.status is EstadoCombate.CONFLICTO
    assert _puntos(ana.id) is None  # el conflicto todavía no cuenta

    combat_services.admin_edit_result(dona.id, combate.id, {"winner_id": beto.id})

    assert combate.status is EstadoCombate.RESUELTO
    assert combate.processed is True
    assert _puntos(ana.id).points == pytest.approx(1490.0)
    assert _puntos(beto.id).points == pytest.approx(1510.0)
    assert len(RatingHistoryRepository.entradas_de_comunidad(1)) == 2


# ---------------------------------------------------------------------------
# 6.4 — ruta POST /admin/ranking/recalculate
# ---------------------------------------------------------------------------


def test_ruta_recalculate_requiere_rol(client, escenario):
    dona = escenario["dona"]
    ana = escenario["ana"]

    r = client.post("/admin/ranking/recalculate")
    assert r.status_code == 401

    client.post("/auth/login", json={"email": ana.email, "password": "password123"})
    assert client.post("/admin/ranking/recalculate").status_code == 403
    client.post("/auth/logout")

    client.post("/auth/login", json={"email": dona.email, "password": "password123"})
    r = client.post("/admin/ranking/recalculate")
    assert r.status_code == 200
    assert r.get_json() == {"community_id": 1, "combats_processed": 0}


def test_ruta_recalculate_reconstruye_desde_cero(client, escenario):
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate = _reportar(ana, [ana, beto], ana)
    combate.status = EstadoCombate.CONFIRMADO
    ranking_services.process_confirmed_combat(combate.id)
    assert _puntos(ana.id).matches_played == 1

    # Se corrompe el índice a mano: el recálculo debe restaurarlo.
    rating = _puntos(ana.id)
    rating.points = 9999.0
    db.session.commit()

    client.post("/auth/login", json={"email": dona.email, "password": "password123"})
    r = client.post("/admin/ranking/recalculate")
    assert r.status_code == 200
    assert r.get_json()["combats_processed"] == 1
    assert _puntos(ana.id).points == pytest.approx(1510.0)
    assert _puntos(beto.id).points == pytest.approx(1490.0)
    assert len(RatingHistoryRepository.entradas_de_comunidad(1)) == 2


# ---------------------------------------------------------------------------
# 6.6 — atomicidad del recálculo completo y defensas del servicio
# ---------------------------------------------------------------------------


def test_atomicidad_del_recalculo_completo(escenario, monkeypatch):
    """Fallo durante el replay → se restauran ratings, historial y combates."""
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    combate.status = EstadoCombate.CONFIRMADO
    ranking_services.process_confirmed_combat(combate.id)
    puntos_antes = _puntos(ana.id).points

    def _fallar(entry):
        raise RuntimeError("fallo simulado en el recálculo completo")

    monkeypatch.setattr(
        ranking_services.RatingHistoryRepository, "add", _fallar
    )
    with pytest.raises(RuntimeError, match="recálculo completo"):
        ranking_services.recalculate_full(1)

    # Rollback completo: nada cambió en la BD.
    assert _puntos(ana.id).points == pytest.approx(puntos_antes)
    assert len(RatingHistoryRepository.entradas_de_comunidad(1)) == 2
    assert combate.processed is True


def test_duelo_rechaza_resultado_invalido(escenario):
    """Un combate sin una victoria/derrota inequívoca no se puede procesar."""
    from app.modules.combat.domain.estados import ResultadoParticipante

    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    for participante in combate.participants:
        participante.result = ResultadoParticipante.VICTORIA
    db.session.commit()

    with pytest.raises(DomainError, match="resultado válido"):
        ranking_services.procesar_duelo(combate, {})


def test_duelo_rechaza_combate_sin_dos_participantes(escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    db.session.delete(combate.participants[1])
    db.session.commit()

    with pytest.raises(DomainError, match="exactamente 2 participantes"):
        ranking_services.procesar_duelo(combate, {})


def test_percentil_de_comunidad_vacia():
    assert ranking_services._percentil(1, {}) == 0.0

