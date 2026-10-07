"""Tests de la edición manual admin y su auditoría (Sprint 5.4 y 5.6)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services
from app.modules.combat.domain.estados import EstadoCombate, ResultadoParticipante
from app.modules.combat.models import AuditLog
from app.modules.combat.repositories import AuditLogRepository
from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository
from app.shared.errors import DomainError, ForbiddenError, NotFoundError

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
    return services.report_combat(
        reporter_id=reporter.id,
        participants=[u.id for u in participantes],
        winner=ganador.id,
        played_at=AYER,
        **extra,
    )


def _campos(combat_id):
    return [e.campo for e in AuditLogRepository.entradas_de(combat_id)]


def test_admin_cambia_ganador_y_queda_resuelto(escenario):
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate, _ = _reportar(ana, [ana, beto], ana)
    servicios = services.admin_edit_result(dona.id, combate.id, {"winner_id": beto.id})

    assert servicios.status is EstadoCombate.RESUELTO
    assert servicios.ganador_id == beto.id
    assert servicios.participants[0].result is ResultadoParticipante.DERROTA
    assert _campos(combate.id) == ["winner_id", "status"]
    entrada = AuditLogRepository.entradas_de(combate.id)[0]
    assert entrada.admin_id == dona.id
    assert entrada.valor_anterior == str(ana.id)
    assert entrada.valor_nuevo == str(beto.id)


def test_admin_edita_combate_ya_resuelto(escenario):
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate, _ = _reportar(ana, [ana, beto], ana)
    services.admin_edit_result(dona.id, combate.id, {"winner_id": beto.id})

    services.admin_edit_result(dona.id, combate.id, {"winner_id": ana.id})
    assert combate.status is EstadoCombate.RESUELTO
    assert combate.ganador_id == ana.id
    assert _campos(combate.id) == ["winner_id", "status", "winner_id"]


def test_admin_resuelve_conflicto_sin_cambiar_ganador(escenario):
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate, _ = _reportar(ana, [ana, beto], ana)
    services.confirm_combat(ana.id, combate.id, ana.id)
    services.confirm_combat(beto.id, combate.id, beto.id)
    assert combate.status is EstadoCombate.CONFLICTO

    combate = services.admin_edit_result(dona.id, combate.id, {})
    assert combate.status is EstadoCombate.RESUELTO
    assert _campos(combate.id) == ["status"]
    entrada = AuditLogRepository.entradas_de(combate.id)[0]
    assert entrada.campo == "status"
    assert entrada.valor_anterior == "CONFLICTO"


def test_admin_sin_cambios_en_resuelto_es_error(escenario):
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate, _ = _reportar(ana, [ana, beto], ana)
    services.admin_edit_result(dona.id, combate.id, {"winner_id": beto.id})

    with pytest.raises(DomainError, match="sin cambios|no tiene cambios"):
        services.admin_edit_result(dona.id, combate.id, {"winner_id": beto.id})


def test_campo_no_editable(escenario):
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate, _ = _reportar(ana, [ana, beto], ana)
    with pytest.raises(DomainError, match="no es editable"):
        services.admin_edit_result(dona.id, combate.id, {"community_id": 9})


def test_ganador_que_no_es_participante(escenario):
    ana, beto, dona, caro = (
        escenario["ana"],
        escenario["beto"],
        escenario["dona"],
        escenario["caro"],
    )
    combate, _ = _reportar(ana, [ana, beto], ana)
    with pytest.raises(DomainError, match="winner_id"):
        services.admin_edit_result(dona.id, combate.id, {"winner_id": caro.id})


def test_no_admin_no_edita(escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    combate, _ = _reportar(ana, [ana, beto], ana)
    with pytest.raises(ForbiddenError, match="administrador"):
        services.admin_edit_result(ana.id, combate.id, {"winner_id": beto.id})
    assert combate.status is EstadoCombate.PENDIENTE
    assert AuditLogRepository.entradas_de(combate.id) == []


def test_combate_inexistente(escenario):
    dona = escenario["dona"]
    with pytest.raises(NotFoundError, match="combate"):
        services.admin_edit_result(dona.id, 4242, {"winner_id": 1})


def test_admin_edita_fecha_y_arbitro(escenario):
    ana, beto, caro, dona = (
        escenario["ana"],
        escenario["beto"],
        escenario["caro"],
        escenario["dona"],
    )
    combate, _ = _reportar(ana, [ana, beto], ana)
    nueva_fecha = AYER - timedelta(days=3)
    services.admin_edit_result(
        dona.id,
        combate.id,
        {"played_at": nueva_fecha.isoformat(), "referee_id": caro.id},
    )
    assert combate.played_at == nueva_fecha
    assert combate.referee_id == caro.id
    assert _campos(combate.id) == ["played_at", "referee_id", "status"]

    # y se puede desasignar el árbitro pasando null
    services.admin_edit_result(dona.id, combate.id, {"referee_id": None})
    assert combate.referee_id is None
    assert _campos(combate.id)[-1] == "referee_id"


def test_admin_de_otra_comunidad_no_edita(escenario):
    """RNF006: un admin solo edita combates de su propia comunidad."""
    ana, beto = escenario["ana"], escenario["beto"]
    ajena = _usuario("otra@x.com", "Ajena Ruiz", rol="admin", comunidad=2)
    combate, _ = _reportar(ana, [ana, beto], ana)

    with pytest.raises(ForbiddenError, match="comunidad"):
        services.admin_edit_result(ajena.id, combate.id, {"winner_id": beto.id})

    assert combate.status is EstadoCombate.PENDIENTE
    assert AuditLogRepository.entradas_de(combate.id) == []

