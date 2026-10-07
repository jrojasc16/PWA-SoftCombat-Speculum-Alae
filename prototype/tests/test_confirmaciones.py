"""Tests de confirmaciones de combate (Sprint 5.2 y 5.6).

Cubre las reglas del RF8: dos participantes coincidentes/conflictivos, la
prioridad del árbitro, el "una sola vez" por usuario y los permisos.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services
from app.modules.combat.domain.estados import EstadoCombate, ResultadoParticipante
from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository
from app.shared.errors import ConflictError, DomainError, NotFoundError

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
    return {"ana": ana, "beto": beto, "caro": caro}


def _reportar(reporter, participantes, ganador, **extra):
    return services.report_combat(
        reporter_id=reporter.id,
        participants=[u.id for u in participantes],
        winner=ganador.id,
        played_at=AYER,
        **extra,
    )


def _sonar(escenario, **extra):
    ana, beto = escenario["ana"], escenario["beto"]
    combate, _ = _reportar(ana, [ana, beto], ana, **extra)
    return combate


def test_dos_confirmaciones_coincidentes_cierran(escenario):
    combate = _sonar(escenario)
    ana, beto = escenario["ana"], escenario["beto"]
    services.confirm_combat(ana.id, combate.id, {"winner_id": ana.id})
    assert combate.status is EstadoCombate.PENDIENTE
    services.confirm_combat(beto.id, combate.id, ana.id)
    assert combate.status is EstadoCombate.CONFIRMADO
    assert combate.ganador_id == ana.id


def test_dos_confirmaciones_discrepantes_generan_conflicto(escenario):
    combate = _sonar(escenario)
    ana, beto = escenario["ana"], escenario["beto"]
    services.confirm_combat(ana.id, combate.id, ana.id)
    services.confirm_combat(beto.id, combate.id, beto.id)
    assert combate.status is EstadoCombate.CONFLICTO


def test_arbitro_prevalece_sobre_participantes(escenario):
    combate = _sonar(escenario, referee_id=escenario["caro"].id)
    ana, beto, caro = escenario["ana"], escenario["beto"], escenario["caro"]
    services.confirm_combat(ana.id, combate.id, ana.id)
    services.confirm_combat(beto.id, combate.id, beto.id)
    assert combate.status is EstadoCombate.CONFLICTO
    services.confirm_combat(caro.id, combate.id, beto.id)
    assert combate.status is EstadoCombate.CONFIRMADO
    assert combate.ganador_id == beto.id
    assert combate.participants[0].result is ResultadoParticipante.DERROTA


def test_arbitro_cierra_en_confirmando_aun_sin_conflicto(escenario):
    combate = _sonar(escenario, referee_id=escenario["caro"].id)
    ana, caro = escenario["ana"], escenario["caro"]
    services.confirm_combat(caro.id, combate.id, ana.id)
    assert combate.status is EstadoCombate.CONFIRMADO


def test_doble_confirmacion_es_conflicto(escenario):
    from app.modules.combat.models import Confirmation

    combate = _sonar(escenario)
    ana, beto = escenario["ana"], escenario["beto"]
    services.confirm_combat(ana.id, combate.id, ana.id)
    with pytest.raises(ConflictError):
        services.confirm_combat(ana.id, combate.id, beto.id)
    assert (
        db.session.query(Confirmation).filter_by(combat_id=combate.id).count() == 1
    )


def test_tercero_no_confirma(escenario):
    combate = _sonar(escenario)
    molesta = _usuario("molesta@x.com", "Molesta")
    with pytest.raises(DomainError, match="participante"):
        services.confirm_combat(molesta.id, combate.id, molesta.id)


def test_arbitro_sin_asignar_no_confirma(escenario):
    combate = _sonar(escenario)  # sin referee_id
    caro = escenario["caro"]
    with pytest.raises(DomainError, match="participante"):
        services.confirm_combat(caro.id, combate.id, caro.id)


def test_winner_no_participante(escenario):
    combate = _sonar(escenario)
    ana = escenario["ana"]
    with pytest.raises(DomainError, match="winner_id"):
        services.confirm_combat(ana.id, combate.id, 9999)


def test_combate_cerrado_no_admite_confirmacion(escenario):
    combate = _sonar(escenario)
    ana, beto = escenario["ana"], escenario["beto"]
    services.confirm_combat(ana.id, combate.id, ana.id)
    services.confirm_combat(beto.id, combate.id, ana.id)
    otro = _usuario("otro@x.com", "Otro")
    with pytest.raises(DomainError, match="cerrado"):
        services.confirm_combat(otro.id, combate.id, ana.id)


def test_combate_inexistente(escenario):
    with pytest.raises(NotFoundError, match="combate"):
        services.confirm_combat(escenario["ana"].id, 4242, escenario["ana"].id)
