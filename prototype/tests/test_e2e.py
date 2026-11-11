"""Suite de integración end-to-end (Sprint 12.3).

Recorre el ciclo de vida completo de un combate contra la API real, sin
atajos de dominio: registro → directorio → reporte → confirmación dual →
Elo on-write → historial → endpoint público. Cubre también el camino de
conflicto (dos confirmaciones discrepantes) resuelto desde el panel de
administración con su bitácora y el recálculo manual.

A diferencia de los tests unitarios, aquí solo se habla por HTTP con los
clientes de pruebas: cualquier rotura de contrato entre capas se ve.
"""

from app.extensions import db

# Fecha pasada y fija: el backend rechaza combates con fecha futura.
FECHA_COMBATE = "2026-11-01T18:00:00"


def _registrar(cliente, email, nombre, password="password123"):
    """Registra una cuenta por la API y devuelve su perfil (sesión iniciada)."""
    r = cliente.post(
        "/auth/register",
        json={"email": email, "password": password, "name": nombre},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


def _rol_de(email: str, nombre_rol: str):
    """Asigna un rol a la cuenta con ese correo (el registro solo da jugador)."""
    from app.modules.iam.repositories import RoleRepository, UserRepository

    usuario = UserRepository.get_by_email(email)
    assert usuario is not None, f"no existe la cuenta {email}"
    usuario.role_id = RoleRepository.get_by_name(nombre_rol).id
    db.session.commit()
    return usuario


def _reportar(cliente, participantes, ganador, clave=None):
    """Reporta un combate y devuelve (respuesta, id)."""
    cuerpo = {
        "participants": participantes,
        "winner": ganador,
        "played_at": FECHA_COMBATE,
    }
    if clave is not None:
        cuerpo["client_request_id"] = clave
    r = cliente.post("/combats", json=cuerpo)
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    return r


# ---------------------------------------------------------------------------
# Camino feliz: de un registro a un combate con Elo en el ranking público
# ---------------------------------------------------------------------------


def test_e2e_un_combate_completo_del_registro_al_ranking_publico(app, client, roles):
    # --- 1. Registro de los dos jugadores (sesiones independientes) ---------
    ana = _registrar(client, "ana@speculum.test", "Ana Rojas")
    cliente_beto = app.test_client()
    beto = _registrar(cliente_beto, "beto@speculum.test", "Beto Pérez")

    r = client.get("/me")
    assert r.status_code == 200
    assert r.get_json()["email"] == "ana@speculum.test"

    # --- 2. Directorio de comunidad (nombre → id, sin correos) --------------
    directorio_respuesta = client.get("/me/community")
    directorio = directorio_respuesta.get_json()
    assert directorio["yo"]["id"] == ana["id"]
    assert beto["id"] in {m["id"] for m in directorio["jugadores"]}
    # El directorio solo expone id y nombre: nunca correos (RNF de datos).
    assert "@" not in directorio_respuesta.get_data(as_text=True)

    # --- 3. Reporte del combate (queda PENDIENTE) ---------------------------
    r = _reportar(client, [ana["id"], beto["id"]], ana["id"], clave="e2e-001")
    assert r.status_code == 201
    combate = r.get_json()
    assert combate["status"] == "PENDIENTE"
    assert combate["processed"] is False
    combate_id = combate["id"]

    # --- 4. Idempotencia: reenviar la misma clave no duplica (RF5) ----------
    r = _reportar(client, [ana["id"], beto["id"]], ana["id"], clave="e2e-001")
    assert r.status_code == 200
    assert r.get_json()["id"] == combate_id

    # --- 5. Beto ve el combate pendiente y aún no hay Elo -------------------
    pendientes = cliente_beto.get("/combats/pending").get_json()
    assert [c["id"] for c in pendientes] == [combate_id]

    r = client.get(f"/combats/{combate_id}")
    assert r.status_code == 200
    assert r.get_json()["status"] == "PENDIENTE"

    # --- 6. Confirmación dual coincidente → CONFIRMADO + Elo on-write -------
    r = client.post(f"/combats/{combate_id}/confirm", json={"winner_id": ana["id"]})
    assert r.status_code == 200
    assert r.get_json()["status"] == "PENDIENTE"  # una sola confirmación no basta

    # Mientras el combate siga abierto, repetir la confirmación da 409.
    r = client.post(f"/combats/{combate_id}/confirm", json={"winner_id": ana["id"]})
    assert r.status_code == 409
    assert "error" in r.get_json()

    r = cliente_beto.post(f"/combats/{combate_id}/confirm", json={"winner_id": ana["id"]})
    assert r.status_code == 200
    cerrado = r.get_json()
    assert cerrado["status"] == "CONFIRMADO"
    assert cerrado["processed"] is True

    # Cerrado el combate, cualquier confirmación nueva es 400 (ya cerrado).
    r = client.post(f"/combats/{combate_id}/confirm", json={"winner_id": ana["id"]})
    assert r.status_code == 400
    assert "error" in r.get_json()

    # --- 7. Ranking público: los índices cambiaron (sin correos) ------------
    cliente_publico = app.test_client()
    r = cliente_publico.get("/api/ranking")
    assert r.status_code == 200
    assert r.headers.get("Cache-Control", "").startswith("public")
    cuerpo = r.get_data(as_text=True)
    assert "ana@speculum.test" not in cuerpo and "beto@speculum.test" not in cuerpo

    ranking = r.get_json()
    assert ranking["total"] == 2
    por_nombre = {i["name"]: i for i in ranking["items"]}
    assert por_nombre["Ana Rojas"]["points"] > 1500  # ganadora sube
    assert por_nombre["Beto Pérez"]["points"] < 1500  # perdedor baja
    assert all(i["matches_played"] == 1 for i in ranking["items"])
    assert ranking["items"][0]["position"] == 1

    # --- 8. Historial propio con la variación Elo ---------------------------
    historial = client.get("/me/history").get_json()
    assert historial["total"] == 1
    assert historial["rating"]["points"] > 1500
    item = historial["items"][0]
    assert item["combat_id"] == combate_id
    assert item["opponent"]["name"] == "Beto Pérez"
    assert item["result"] == "VICTORIA"
    assert item["rating"]["delta"] > 0
    assert item["rating"]["points_after"] > item["rating"]["points_before"]

    historial_beto = cliente_beto.get("/me/history").get_json()
    assert historial_beto["items"][0]["result"] == "DERROTA"
    assert historial_beto["items"][0]["rating"]["delta"] < 0

    # --- 9. Cierre de sesión: la API vuelve a exigir autenticación ----------
    r = client.post("/auth/logout")
    assert r.status_code == 200
    assert client.get("/me").status_code == 401


# ---------------------------------------------------------------------------
# Camino de conflicto: dos confirmaciones discrepantes → panel de admin
# ---------------------------------------------------------------------------


def test_e2e_un_conflicto_se_resuelve_desde_el_panel_de_administracion(
    app, client, roles
):
    # --- Jugadores y un administrador --------------------------------------
    ana = _registrar(client, "ana2@speculum.test", "Ana Rojas")
    cliente_beto = app.test_client()
    beto = _registrar(cliente_beto, "beto2@speculum.test", "Beto Pérez")
    cliente_admin = app.test_client()
    _registrar(cliente_admin, "dana2@speculum.test", "Dana Admin")
    _rol_de("dana2@speculum.test", "admin")

    # --- Reporte y confirmaciones discrepantes → CONFLICTO ------------------
    combate_id = _reportar(client, [ana["id"], beto["id"]], ana["id"]).get_json()["id"]
    r = client.post(f"/combats/{combate_id}/confirm", json={"winner_id": ana["id"]})
    assert r.get_json()["status"] == "PENDIENTE"
    r = cliente_beto.post(f"/combats/{combate_id}/confirm", json={"winner_id": beto["id"]})
    assert r.get_json()["status"] == "CONFLICTO"

    # --- El admin lista los conflictos de su comunidad ----------------------
    r = cliente_admin.get("/admin/combats?status=CONFLICTO")
    assert r.status_code == 200
    assert combate_id in [c["id"] for c in r.get_json()]

    # Un jugador no puede entrar al panel (RBAC): 401/403, nunca 200.
    assert client.get("/admin/combats?status=CONFLICTO").status_code == 403

    # --- Resolución: el admin declara ganador real a Beto (no al reportado) --
    r = cliente_admin.patch(
        f"/admin/combats/{combate_id}", json={"winner_id": beto["id"]}
    )
    assert r.status_code == 200
    resuelto = r.get_json()
    assert resuelto["status"] == "RESUELTO"
    assert resuelto["processed"] is True  # la edición admin recalcula el Elo
    # La proyección pública no trae `winner_id`: el ganador se ve en los resultados.
    victorias = [
        p["user_id"] for p in resuelto["participants"] if p["result"] == "VICTORIA"
    ]
    assert victorias == [beto["id"]]

    # --- Bitácora con los campos tocados (RNF008) ---------------------------
    r = cliente_admin.get(f"/admin/combats/{combate_id}/audit")
    assert r.status_code == 200
    por_campo = {entrada["campo"]: entrada for entrada in r.get_json()}
    assert {"winner_id", "status"} <= set(por_campo)
    assert por_campo["winner_id"]["valor_anterior"] == str(ana["id"])
    assert por_campo["winner_id"]["valor_nuevo"] == str(beto["id"])
    assert por_campo["status"]["valor_anterior"] == "CONFLICTO"
    assert por_campo["status"]["valor_nuevo"] == "RESUELTO"

    # --- El ranking público refleja el resultado resuelto -------------------
    r = app.test_client().get("/api/ranking")
    por_nombre = {i["name"]: i for i in r.get_json()["items"]}
    assert por_nombre["Beto Pérez"]["points"] > por_nombre["Ana Rojas"]["points"]
    assert por_nombre["Beto Pérez"]["matches_played"] == 1
    puntos_antes = {i["name"]: i["points"] for i in r.get_json()["items"]}

    # --- Y el recálculo manual sigue siendo coherente -----------------------
    r = cliente_admin.post("/admin/ranking/recalculate")
    assert r.status_code == 200
    assert r.get_json()["combats_processed"] >= 1

    # Tras recalcular, el ranking sigue diciendo lo mismo (replay estable).
    r2 = app.test_client().get("/api/ranking")
    assert {i["name"]: i["points"] for i in r2.get_json()["items"]} == puntos_antes


# ---------------------------------------------------------------------------
# Contratos transversales que la suite e2e garantiza de paso
# ---------------------------------------------------------------------------


def test_e2e_sin_sesion_todo_endpoint_protegido_responde_401(app):
    """Ningún endpoint JSON redirige: siempre 401 con `{"error": …}`."""
    anonimo = app.test_client()
    protegidos = [
        ("GET", "/me"),
        ("GET", "/me/community"),
        ("GET", "/me/history"),
        ("GET", "/combats/pending"),
        ("GET", "/combats/1"),
        ("POST", "/combats"),
        ("GET", "/admin/users"),
        ("GET", "/admin/combats"),
        ("GET", "/admin/combats/1/audit"),
        ("POST", "/admin/ranking/recalculate"),
    ]
    for metodo, ruta in protegidos:
        r = anonimo.open(ruta, method=metodo, json={} if metodo == "POST" else None)
        assert r.status_code == 401, f"{metodo} {ruta} → {r.status_code}"
        assert r.is_json, f"{metodo} {ruta} no respondió JSON"
        assert "error" in r.get_json()
        assert r.headers.get("Location") is None, f"{metodo} {ruta} redirigió"
