"""Tests del panel de administración (Sprint 10.5).

Cubre el control de acceso de **todas** las rutas nuevas (HTML y JSON) por
rol y por comunidad (RNF006), la gestión de usuarios (UC10/UC11), la
resolución de conflictos con bitácora visible (UC12) y el recálculo manual
(UC13).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.combat import services as combat_services
from app.modules.combat.repositories import AuditLogRepository
from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository, UserRepository

AYER = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)

# Páginas HTML del panel.
RUTAS_PANEL = ("/admin", "/admin/panel/usuarios", "/admin/panel/combates")

# Endpoints JSON de administración.
RUTAS_ADMIN_JSON = ("/admin/users", "/admin/combats")


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


def _salir(client):
    client.get("/salir")


@pytest.fixture
def escenario(roles):
    ana = _usuario("ana@x.com", "Ana Rojas")
    beto = _usuario("beto@x.com", "Beto Sanz")
    caro = _usuario("caro@x.com", "Caro Diaz", rol="arbitro")
    dona = _usuario("dona@x.com", "Dona Eva", rol="admin")
    root = _usuario("root@x.com", "Root Ana", rol="super_admin")
    otro = _usuario("otro@x.com", "Otro Admin", rol="admin", comunidad=2)
    return {
        "ana": ana,
        "beto": beto,
        "caro": caro,
        "dona": dona,
        "root": root,
        "otro": otro,
    }


def _conflicto(ana, beto):
    """Crea un combate en estado CONFLICTO (las confirmaciones discrepan)."""
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
    return combate


# ---------------------------------------------------------------------------
# Control de acceso de las páginas HTML del panel
# ---------------------------------------------------------------------------


def test_paginas_panel_requieren_sesion(client, escenario):
    """Sin sesión, el panel redirige al login conservando la ruta de destino."""
    for ruta in RUTAS_PANEL:
        r = client.get(ruta)
        assert r.status_code == 302, ruta
        assert "/login" in r.headers["Location"]
        assert f"next={ruta}" in r.headers["Location"]


def test_paginas_panel_403_para_jugador(client, escenario):
    """Un jugador autenticado recibe la página de "sin permisos" (403)."""
    _login(client, escenario["ana"])

    for ruta in RUTAS_PANEL:
        r = client.get(ruta)
        assert r.status_code == 403, ruta
        assert "No tienes permisos" in r.get_data(as_text=True)


def test_paginas_panel_200_para_admin(client, escenario):
    """El admin y el super_admin acceden al panel."""
    _login(client, escenario["dona"])
    for ruta in RUTAS_PANEL:
        assert client.get(ruta).status_code == 200, ruta

    _salir(client)
    _login(client, escenario["root"])
    for ruta in RUTAS_PANEL:
        assert client.get(ruta).status_code == 200, ruta


def test_navegacion_muestra_enlace_admin_solo_a_admins(client, escenario):
    """El enlace "Admin" solo aparece para los roles con acceso al panel."""
    _login(client, escenario["ana"])
    assert "Admin" not in client.get("/ranking").get_data(as_text=True)

    _salir(client)
    _login(client, escenario["dona"])
    texto = client.get("/ranking").get_data(as_text=True)
    assert "/admin" in texto


# ---------------------------------------------------------------------------
# Control de acceso de los endpoints JSON de administración
# ---------------------------------------------------------------------------


def test_admin_json_requiere_sesion(client, escenario):
    """Sin sesión, los endpoints JSON de admin responden 401."""
    assert client.get("/admin/users").status_code == 401
    assert client.get("/admin/combats").status_code == 401
    assert client.get("/admin/combats/1/audit").status_code == 401
    assert client.patch("/admin/users/1", json={"active": False}).status_code == 401


def test_admin_json_403_para_jugador(client, escenario):
    """Un jugador autenticado recibe 403 en los endpoints JSON de admin."""
    _login(client, escenario["ana"])

    assert client.get("/admin/users").status_code == 403
    assert client.get("/admin/combats").status_code == 403
    assert client.get("/admin/combats/1/audit").status_code == 403
    assert client.patch("/admin/users/2", json={"active": False}).status_code == 403


def test_admin_json_200_para_admin(client, escenario):
    """El admin accede a los endpoints JSON de su comunidad."""
    _login(client, escenario["dona"])

    r = client.get("/admin/users")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)

    assert client.get("/admin/combats").status_code == 200


def test_admin_json_no_ve_usuarios_de_otra_comunidad(client, escenario):
    """RNF006: el listado de usuarios está acotado a la comunidad del admin."""
    _login(client, escenario["dona"])

    ids = {u["id"] for u in client.get("/admin/users").get_json()}
    assert escenario["dona"].id in ids
    assert escenario["otro"].id not in ids


def test_admin_json_no_ve_combates_de_otra_comunidad(client, escenario):
    """RNF006: los combates listados son solo los de la comunidad del admin."""
    _login(client, escenario["dona"])

    rival_externo = _usuario("rival2@x.com", "Rival Externo", comunidad=2)
    combate_otro, _ = combat_services.report_combat(
        reporter_id=escenario["otro"].id,
        participants=[escenario["otro"].id, rival_externo.id],
        winner=escenario["otro"].id,
        played_at=AYER,
    )
    _salir(client)
    _login(client, escenario["dona"])

    ids = {c["id"] for c in client.get("/admin/combats").get_json()}
    assert combate_otro.id not in ids


# ---------------------------------------------------------------------------
# Gestión de usuarios (UC10/UC11)
# ---------------------------------------------------------------------------


def test_listado_usuarios_incluye_inactivos(client, escenario):
    """El listado del panel incluye las cuentas desactivadas."""
    beto = escenario["beto"]
    beto.active = False
    db.session.commit()

    _login(client, escenario["dona"])
    usuarios = {u["id"]: u for u in client.get("/admin/users").get_json()}
    assert usuarios[beto.id]["active"] is False


def test_desactivar_usuario_impide_iniciar_sesion(client, escenario):
    """Desactivar una cuenta la saca del circuito de autenticación."""
    _login(client, escenario["dona"])

    r = client.patch(
        f"/admin/users/{escenario['beto'].id}", json={"active": False}
    )
    assert r.status_code == 200
    assert r.get_json()["active"] is False

    _salir(client)
    r = client.post(
        "/auth/login",
        json={"email": escenario["beto"].email, "password": "password123"},
    )
    assert r.status_code == 401


def test_activar_usuario_devuelve_el_acceso(client, escenario):
    """Reactivar una cuenta vuelve a permitir el inicio de sesión."""
    beto = escenario["beto"]
    beto.active = False
    db.session.commit()

    _login(client, escenario["dona"])
    r = client.patch(f"/admin/users/{beto.id}", json={"active": True})
    assert r.status_code == 200
    assert r.get_json()["active"] is True

    _salir(client)
    r = client.post(
        "/auth/login", json={"email": beto.email, "password": "password123"}
    )
    assert r.status_code == 200


def test_cambiar_rol_desde_la_api(client, escenario):
    """Cambiar el rol se refleja en la respuesta y en la base de datos."""
    _login(client, escenario["dona"])

    r = client.patch(
        f"/admin/users/{escenario['beto'].id}", json={"role": "arbitro"}
    )
    assert r.status_code == 200
    assert r.get_json()["role"] == "arbitro"

    beto = UserRepository.get_by_id(escenario["beto"].id)
    assert beto.role.name == "arbitro"


def test_admin_no_puede_asignar_super_admin(client, escenario):
    """Solo un super_admin concede el rol super_admin (sin escalamiento)."""
    _login(client, escenario["dona"])

    r = client.patch(
        f"/admin/users/{escenario['beto'].id}", json={"role": "super_admin"}
    )
    assert r.status_code == 403
    assert "super administrador" in r.get_json()["error"].lower()

    beto = UserRepository.get_by_id(escenario["beto"].id)
    assert beto.role.name == "jugador"


def test_super_admin_si_puede_asignar_super_admin(client, escenario):
    """El super_admin sí puede promover a otro usuario."""
    _login(client, escenario["root"])

    r = client.patch(
        f"/admin/users/{escenario['beto'].id}", json={"role": "super_admin"}
    )
    assert r.status_code == 200
    assert r.get_json()["role"] == "super_admin"


def test_admin_no_puede_desactivarse_a_si_mismo(client, escenario):
    """Auto-desactivarse dejaría al admin sin acceso al panel."""
    _login(client, escenario["dona"])

    r = client.patch(
        f"/admin/users/{escenario['dona'].id}", json={"active": False}
    )
    assert r.status_code == 403
    assert "tu propia cuenta" in r.get_json()["error"].lower()


def test_admin_no_puede_cambiarse_a_si_mismo_el_rol(client, escenario):
    """Un admin no se degrada a sí mismo por accidente."""
    _login(client, escenario["dona"])

    r = client.patch(
        f"/admin/users/{escenario['dona'].id}", json={"role": "jugador"}
    )
    assert r.status_code == 403

    dona = UserRepository.get_by_id(escenario["dona"].id)
    assert dona.role.name == "admin"


def test_admin_no_gestiona_usuarios_de_otra_comunidad(client, escenario):
    """RNF006: un admin no toca cuentas de otra comunidad."""
    _login(client, escenario["dona"])

    r = client.patch(
        f"/admin/users/{escenario['otro'].id}", json={"active": False}
    )
    assert r.status_code == 403
    assert "otra comunidad" in r.get_json()["error"].lower()

    otro = UserRepository.get_by_id(escenario["otro"].id)
    assert otro.active is True


def test_usuario_inexistente_responde_404(client, escenario):
    """Gestionar un id inexistente devuelve 404."""
    _login(client, escenario["dona"])

    assert client.patch("/admin/users/99999", json={"active": False}).status_code == 404


def test_rol_inexistente_responde_400(client, escenario):
    """Un rol que no existe en la tabla de roles se rechaza."""
    _login(client, escenario["dona"])

    r = client.patch(
        f"/admin/users/{escenario['beto'].id}", json={"role": "mago"}
    )
    assert r.status_code == 400
    assert "no existe" in r.get_json()["error"].lower()


def test_sin_campos_responde_400(client, escenario):
    """Una petición sin 'active' ni 'role' se rechaza con 400."""
    _login(client, escenario["dona"])

    r = client.patch(f"/admin/users/{escenario['beto'].id}", json={})
    assert r.status_code == 400


def test_admin_users_acepta_formulario(client, escenario):
    """El formulario web (POST) funciona igual que el PATCH de la API."""
    _login(client, escenario["dona"])

    r = client.post(
        f"/admin/users/{escenario['beto'].id}",
        data={"_method": "PATCH", "active": "0"},
    )
    assert r.status_code == 200
    assert r.get_json()["active"] is False


# ---------------------------------------------------------------------------
# Combates en conflicto y bitácora (UC12)
# ---------------------------------------------------------------------------


def test_pagina_combates_lista_los_conflictos(client, escenario):
    """La página de combates muestra los que están en CONFLICTO."""
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    conflicto = _conflicto(ana, beto)

    _login(client, dona)
    r = client.get("/admin/panel/combates")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert f"Combate #{conflicto.id}" in texto
    assert "Ana Rojas" in texto
    assert "Ganador real" in texto


def test_pagina_combates_filtra_por_estado(client, escenario):
    """El filtro de estado cambia el listado (por defecto: CONFLICTO)."""
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    conflicto = _conflicto(ana, beto)

    _login(client, dona)
    r = client.get("/admin/panel/combates?estado=RESUELTO")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert f"Combate #{conflicto.id}" not in texto

    r = client.get("/admin/panel/combates?estado=CONFLICTO")
    assert f"Combate #{conflicto.id}" in r.get_data(as_text=True)


def test_pagina_combates_estado_invalido_responde_400_con_aviso(client, escenario):
    """Un estado desconocido no rompe la página: se avisa y se muestra CONFLICTO."""
    _login(client, escenario["dona"])

    r = client.get("/admin/panel/combates?estado=INVENTADO")
    assert r.status_code == 200
    assert "Estado inválido" in r.get_data(as_text=True)


def test_resolver_conflicto_desde_la_api_deja_auditoria(client, escenario):
    """Editar el resultado de un conflicto lo resuelve y lo audita."""
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    conflicto = _conflicto(ana, beto)

    _login(client, dona)
    r = client.patch(f"/admin/combats/{conflicto.id}", json={"winner_id": beto.id})
    assert r.status_code == 200
    assert r.get_json()["status"] == "RESUELTO"

    campos = [e.campo for e in AuditLogRepository.entradas_de(conflicto.id)]
    assert "winner_id" in campos
    assert "status" in campos


def test_bitacora_visible_en_la_pagina_del_panel(client, escenario):
    """Tras resolver, la bitácora aparece en la página de combates."""
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    conflicto = _conflicto(ana, beto)

    _login(client, dona)
    client.patch(f"/admin/combats/{conflicto.id}", json={"winner_id": beto.id})

    r = client.get("/admin/panel/combates?estado=RESUELTO")
    texto = r.get_data(as_text=True)
    assert "Bitácora de auditoría" in texto
    assert "winner_id" in texto
    assert "Dona Eva" in texto


def test_endpoint_auditoria_devuelve_las_entradas(client, escenario):
    """El endpoint de auditoría devuelve la traza del combate."""
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    conflicto = _conflicto(ana, beto)

    _login(client, dona)
    client.patch(f"/admin/combats/{conflicto.id}", json={"winner_id": beto.id})

    r = client.get(f"/admin/combats/{conflicto.id}/audit")
    assert r.status_code == 200
    entradas = r.get_json()
    assert {e["campo"] for e in entradas} >= {"winner_id", "status"}
    assert entradas[0]["admin_name"] == "Dona Eva"


def test_endpoint_auditoria_de_combate_inexistente_404(client, escenario):
    """La bitácora de un combate inexistente devuelve 404."""
    _login(client, escenario["dona"])
    assert client.get("/admin/combats/99999/audit").status_code == 404


def test_admin_no_consulta_la_bitacora_de_otra_comunidad(client, escenario):
    """RNF006: la bitácora de otro comunidad no se puede leer."""
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    conflicto = _conflicto(ana, beto)

    _login(client, dona)
    client.patch(f"/admin/combats/{conflicto.id}", json={"winner_id": beto.id})

    _salir(client)
    _login(client, escenario["otro"])
    r = client.get(f"/admin/combats/{conflicto.id}/audit")
    assert r.status_code == 403
    assert "otra comunidad" in r.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Recálculo manual del ranking (UC13)
# ---------------------------------------------------------------------------


def test_recalcular_ranking_desde_el_panel(client, escenario):
    """El botón de recálculo llama a la API y devuelve el nº de combates."""
    ana, beto, dona = escenario["ana"], escenario["beto"], escenario["dona"]
    combate, _ = combat_services.report_combat(
        reporter_id=ana.id,
        participants=[ana.id, beto.id],
        winner=ana.id,
        played_at=AYER,
    )
    combat_services.admin_edit_result(dona.id, combate.id, {"winner_id": beto.id})

    _login(client, dona)
    r = client.post("/admin/ranking/recalculate")
    assert r.status_code == 200
    cuerpo = r.get_json()
    assert cuerpo["community_id"] == 1
    assert cuerpo["combats_processed"] == 1


def test_recalcular_ranking_requiere_admin(client, escenario):
    """El recálculo manual está reservado a los administradores."""
    _login(client, escenario["ana"])
    assert client.post("/admin/ranking/recalculate").status_code == 403


def test_panel_ofrece_el_boton_de_recalculo(client, escenario):
    """La portada del panel incluye el botón de recálculo con su URL."""
    _login(client, escenario["dona"])

    texto = client.get("/admin").get_data(as_text=True)
    assert 'id="btn-recalcular"' in texto
    assert "/admin/ranking/recalculate" in texto


def test_el_panel_no_se_cachea_en_el_service_worker():
    """Las páginas de administración nunca se guardan en la caché del SW."""
    from pathlib import Path

    sw = (Path(__file__).parent.parent / "app" / "static" / "sw.js").read_text(
        encoding="utf-8"
    )
    assert 'url.pathname.startsWith("/admin")' in sw


def test_existen_las_herramientas_de_verificacion_en_navegador():
    """El sprint se puede verificar en un navegador real (Sprint 10)."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    assert (raiz / "scripts" / "verificar_admin_browser.py").exists()
    assert (raiz / "scripts" / "harness_admin.html").exists()
    assert (raiz / "scripts" / "cdp_esperar_resultado.mjs").exists()


def test_la_pagina_de_prueba_cubre_el_flujo_del_panel():
    """La página de prueba recorre el flujo completo del panel."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    html = (raiz / "scripts" / "harness_admin.html").read_text(encoding="utf-8")
    assert "/admin/users" in html
    assert "/admin/combats" in html
    assert "/admin/ranking/recalculate" in html
    assert 'id="resultado"' in html


def test_el_script_de_verificacion_usa_el_protocolo_devtools():
    """El verificador del panel usa el mismo protocolo DevTools que el offline."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    script = (raiz / "scripts" / "verificar_admin_browser.py").read_text(
        encoding="utf-8"
    )
    assert "cdp_esperar_resultado.mjs" in script
    assert "--remote-debugging-port" in script
