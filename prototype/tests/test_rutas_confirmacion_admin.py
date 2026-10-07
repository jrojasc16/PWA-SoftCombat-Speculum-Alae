"""Tests HTTP de las rutas del Sprint 5.5 (confirmación y panel admin)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services
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


def _login(client, usuario):
    r = client.post(
        "/auth/login", json={"email": usuario.email, "password": "password123"}
    )
    assert r.status_code == 200


@pytest.fixture
def escenario(roles):
    ana = _usuario("ana@x.com", "Ana Rojas")
    beto = _usuario("beto@x.com", "Beto Sanz")
    caro = _usuario("caro@x.com", "Caro Diaz", rol="arbitro")
    dona = _usuario("dona@x.com", "Dona Eva", rol="admin")
    return {"ana": ana, "beto": beto, "caro": caro, "dona": dona}


def _reportar(reporter, participantes, ganador, **extra):
    combate, _ = services.report_combat(
        reporter_id=reporter.id,
        participants=[u.id for u in participantes],
        winner=ganador.id,
        played_at=AYER,
        **extra,
    )
    return combate


# ---------------------------------------------------------------------------
# POST /combats/<id>/confirm
# ---------------------------------------------------------------------------


def test_confirm_requiere_sesion(client, escenario):
    combate = _reportar(escenario["ana"], [escenario["ana"], escenario["beto"]], escenario["ana"])
    r = client.post(f"/combats/{combate.id}/confirm", json={"winner_id": 1})
    assert r.status_code == 401
    assert r.get_json() == {"error": "Autenticación requerida."}


def test_confirm_participantes_cierran_combate(client, escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    _login(client, ana)

    r = client.post(f"/combats/{combate.id}/confirm", json={"winner_id": ana.id})
    assert r.status_code == 200
    assert r.get_json()["status"] == "PENDIENTE"
    client.post("/auth/logout")

    _login(client, beto)
    r = client.post(f"/combats/{combate.id}/confirm", json={"winner_id": ana.id})
    assert r.status_code == 200
    assert r.get_json()["status"] == "CONFIRMADO"


def test_confirm_discrepante_genera_conflicto(client, escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    _login(client, ana)
    client.post(f"/combats/{combate.id}/confirm", json={"winner_id": ana.id})
    client.post("/auth/logout")

    _login(client, beto)
    r = client.post(f"/combats/{combate.id}/confirm", json={"winner_id": beto.id})
    assert r.status_code == 200
    assert r.get_json()["status"] == "CONFLICTO"


def test_confirm_arbitro_prevalece(client, escenario):
    ana, beto, caro = escenario["ana"], escenario["beto"], escenario["caro"]
    combate = _reportar(ana, [ana, beto], ana, referee_id=caro.id)
    _login(client, ana)
    client.post(f"/combats/{combate.id}/confirm", json={"winner_id": ana.id})
    client.post("/auth/logout")
    _login(client, beto)
    client.post(f"/combats/{combate.id}/confirm", json={"winner_id": beto.id})
    client.post("/auth/logout")

    _login(client, caro)
    r = client.post(f"/combats/{combate.id}/confirm", json={"winner_id": beto.id})
    assert r.status_code == 200
    assert r.get_json()["status"] == "CONFIRMADO"
    assert r.get_json()["participants"][0]["result"] == "DERROTA"


def test_confirm_duplicado_responde_409(client, escenario):
    ana = escenario["ana"]
    combate = _reportar(ana, [ana, escenario["beto"]], ana)
    _login(client, ana)
    assert client.post(f"/combats/{combate.id}/confirm", json={"winner_id": ana.id}).status_code == 200
    r = client.post(f"/combats/{combate.id}/confirm", json={"winner_id": ana.id})
    assert r.status_code == 409
    assert "ya confirm" in r.get_json()["error"]


def test_confirm_winner_invalido_responde_400(client, escenario):
    ana = escenario["ana"]
    combate = _reportar(ana, [ana, escenario["beto"]], ana)
    _login(client, ana)
    r = client.post(f"/combats/{combate.id}/confirm", json={"winner_id": 9999})
    assert r.status_code == 400
    assert "winner_id" in r.get_json()["error"]


def test_confirm_sin_winner_responde_400(client, escenario):
    ana = escenario["ana"]
    combate = _reportar(ana, [ana, escenario["beto"]], ana)
    _login(client, ana)
    r = client.post(f"/combats/{combate.id}/confirm", json={})
    assert r.status_code == 400
    assert r.get_json()["error"] == "El campo 'winner_id' es obligatorio."


def test_confirm_combate_inexistente_responde_404(client, escenario):
    _login(client, escenario["ana"])
    r = client.post("/combats/99999/confirm", json={"winner_id": 1})
    assert r.status_code == 404


def test_confirm_acepta_formulario(client, escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)
    _login(client, ana)
    r = client.post(f"/combats/{combate.id}/confirm", data={"winner_id": str(beto.id)})
    assert r.status_code == 200
    assert r.get_json()["status"] == "PENDIENTE"


# ---------------------------------------------------------------------------
# PATCH/POST /admin/combats/<id> y GET /admin/combats
# ---------------------------------------------------------------------------


def test_admin_rutas_requieren_rol(client, escenario):
    ana, beto = escenario["ana"], escenario["beto"]
    combate = _reportar(ana, [ana, beto], ana)

    r = client.patch(f"/admin/combats/{combate.id}", json={"winner_id": beto.id})
    assert r.status_code == 401

    _login(client, ana)
    r = client.patch(f"/admin/combats/{combate.id}", json={"winner_id": beto.id})
    assert r.status_code == 403
    assert r.get_json() == {"error": "No tienes permisos para esta acción."}
    r = client.get("/admin/combats")
    assert r.status_code == 403


def test_admin_edita_y_deja_auditoria(client, escenario):
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate = _reportar(ana, [ana, beto], ana)
    _login(client, dona)

    r = client.patch(f"/admin/combats/{combate.id}", json={"winner_id": beto.id})
    assert r.status_code == 200
    cuerpo = r.get_json()
    assert cuerpo["status"] == "RESUELTO"
    assert cuerpo["participants"][0]["result"] == "DERROTA"


def test_admin_post_formulario_con_method(client, escenario):
    """El formulario web manda POST con ``_method``: se ignora y se aplica."""
    from app.modules.combat.repositories import AuditLogRepository

    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate = _reportar(ana, [ana, beto], ana)
    _login(client, dona)

    r = client.post(
        f"/admin/combats/{combate.id}",
        data={"_method": "PATCH", "winner_id": str(beto.id)},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "RESUELTO"
    assert [e.campo for e in AuditLogRepository.entradas_de(combate.id)] == [
        "winner_id",
        "status",
    ]


def test_admin_campo_no_editable_responde_400(client, escenario):
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate = _reportar(ana, [ana, beto], ana)
    _login(client, dona)
    r = client.patch(f"/admin/combats/{combate.id}", json={"community_id": 9})
    assert r.status_code == 400
    assert "no es editable" in r.get_json()["error"]


def test_admin_combate_inexistente_responde_404(client, escenario):
    _login(client, escenario["dona"])
    assert client.patch("/admin/combats/99999", json={"winner_id": 1}).status_code == 404


def test_admin_listado_filtra_por_estado(client, escenario):
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    pendiente = _reportar(ana, [ana, beto], ana)
    cerrado = _reportar(beto, [ana, beto], beto)
    services.admin_edit_result(dona.id, cerrado.id, {"winner_id": ana.id})

    _login(client, dona)
    r = client.get("/admin/combats?status=PENDIENTE")
    assert r.status_code == 200
    assert [c["id"] for c in r.get_json()] == [pendiente.id]

    r = client.get("/admin/combats?status=RESUELTO")
    assert [c["id"] for c in r.get_json()] == [cerrado.id]

    assert len(client.get("/admin/combats").get_json()) == 2


def test_admin_listado_estado_invalido(client, escenario):
    _login(client, escenario["dona"])
    r = client.get("/admin/combats?status=INVENTADO")
    assert r.status_code == 400
    assert "Estado inválido" in r.get_json()["error"]
