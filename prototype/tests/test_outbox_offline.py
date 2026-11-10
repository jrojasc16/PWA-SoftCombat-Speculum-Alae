"""Tests del envío offline con cola IndexedDB (Sprint 9).

Son pruebas de contrato sobre los estáticos del cliente (el navegador no está
disponible en el entorno de ejecución) más las pruebas del servidor que
garantizan la idempotencia de los reenvíos (``client_request_id``).
"""

import json
import re

import pytest

from app.modules.iam import services as iam_services
from app.modules.iam.repositories import RoleRepository
from app.extensions import db


def _usuario(email, nombre, rol="jugador", comunidad=1):
    user = iam_services.register_user(
        email=email, password="password123", name=nombre, community_id=comunidad
    )
    user.role_id = RoleRepository.get_by_name(rol).id
    db.session.commit()
    return user


@pytest.fixture
def jugador(roles):
    return _usuario("ana@x.com", "Ana Rojas")


def _login(client, usuario):
    r = client.post(
        "/auth/login", json={"email": usuario.email, "password": "password123"}
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 9.1 — db.js: wrapper de IndexedDB con store outbox (FIFO)
# ---------------------------------------------------------------------------


def test_db_js_se_sirve_como_javascript(client):
    r = client.get("/static/db.js")
    assert r.status_code == 200
    assert "javascript" in r.content_type
    assert "SAOutbox" in r.get_data(as_text=True)


def test_db_js_usa_indexeddb_con_el_store_outbox(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    assert "indexedDB.open" in js
    assert 'NOMBRE_BD = "speculum-alae"' in js
    assert 'STORE_OUTBOX = "outbox"' in js


def test_db_js_garantiza_el_orden_fifo_de_la_cola(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    # Clave autoincremental: el orden de la cola es el de inserción.
    assert "autoIncrement: true" in js
    assert "a.id || 0) - (b.id || 0)" in js


def test_db_js_guarda_clave_de_idempotencia_y_estado(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    assert "client_request_id" in js
    assert 'createIndex("client_request_id"' in js
    assert "intentos" in js
    assert "last_error" in js
    assert "created_at" in js


def test_db_js_expone_la_api_de_la_cola(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    for funcion in (
        "encolar",
        "listar",
        "actualizar",
        "eliminar",
        "contarPendientes",
    ):
        assert funcion in js


def test_db_js_avisa_si_el_navegador_no_soporta_indexeddb(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    assert "no soporta IndexedDB" in js
    assert "disponible" in js


def test_db_js_guarda_el_directorio_para_poder_reportar_sin_conexion(client):
    js = client.get("/static/db.js").get_data(as_text=True)
    assert 'STORE_DIRECTORIO = "directorio"' in js
    assert "guardarDirectorio" in js
    assert "leerDirectorio" in js


# ---------------------------------------------------------------------------
# 9.2 — Encolar sin red y drenar la cola con reintento y backoff
# ---------------------------------------------------------------------------


def test_sync_js_se_sirve_y_expone_la_api(client):
    r = client.get("/static/js/sync.js")
    assert r.status_code == 200
    assert "javascript" in r.content_type
    js = r.get_data(as_text=True)
    assert "SASync" in js
    assert "sincronizar" in js


def test_sync_js_se_activa_al_evento_online_y_al_abrir_la_app(client):
    js = client.get("/static/js/sync.js").get_data(as_text=True)
    assert 'addEventListener("online"' in js
    assert 'addEventListener("load"' in js


def test_sync_js_drena_la_cola_enviando_a_post_combats(client):
    js = client.get("/static/js/sync.js").get_data(as_text=True)
    assert 'const RUTA_REPORTE = "/combats"' in js
    assert 'method: "POST"' in js
    assert "client_request_id" in js


def test_sync_js_usa_backoff_exponencial_y_respeta_el_orden_fifo(client):
    js = client.get("/static/js/sync.js").get_data(as_text=True)
    assert "Math.pow(2" in js
    assert "ESPERA_MAXIMA_MS" in js
    # Al fallar un envío reintentable se detiene el drenaje (orden FIFO).
    assert "break; // se conserva el orden FIFO de la cola" in js


def test_sync_js_distingue_error_reintentable_de_error_definitivo(client):
    js = client.get("/static/js/sync.js").get_data(as_text=True)
    assert "reintentable" in js
    assert "respuesta.status >= 400 && respuesta.status < 500" in js
    assert 'estado: "error"' in js


def test_reportar_js_encola_el_reporte_cuando_no_hay_red(client):
    js = client.get("/static/js/reportar.js").get_data(as_text=True)
    assert "encolarReporte" in js
    assert "!navigator.onLine" in js
    assert "SASync.encolar" in js
    assert "quedó guardado y se enviará solo" in js


def test_reportar_js_usa_el_directorio_guardado_cuando_no_hay_red(client):
    js = client.get("/static/js/reportar.js").get_data(as_text=True)
    assert "leerDirectorio" in js
    assert "directorio guardado" in js


def test_layout_carga_db_y_sync_antes_de_la_aplicacion(client):
    html = client.get("/").get_data(as_text=True)
    assert "db.js" in html
    assert "js/sync.js" in html
    assert html.index("db.js") < html.index("js/sync.js") < html.index("js/app.js")


def test_al_cerrar_sesion_se_borra_el_directorio_local(client, jugador):
    _login(client, jugador)
    html = client.get("/").get_data(as_text=True)
    assert 'id="enlace-salir"' in html
    js = client.get("/static/js/app.js").get_data(as_text=True)
    assert "borrarDirectorio" in js


# ---------------------------------------------------------------------------
# 9.3 — Idempotencia: el mismo client_request_id nunca crea dos combates
# ---------------------------------------------------------------------------


def _reporte(clave, rival_id, ganador=None):
    """Cuerpo de un reporte con clave de idempotencia."""
    return {
        "participants": [1, rival_id],
        "winner": ganador if ganador is not None else 1,
        "played_at": "2026-11-01T18:00:00",
        "client_request_id": clave,
    }


def test_el_segundo_envio_con_la_misma_clave_no_crea_otro_combate(
    client, jugador, roles
):
    rival = _usuario("beto@x.com", "Beto Ruiz")
    _login(client, jugador)

    primero = client.post("/combats", json=_reporte("clave-abc-123", rival.id))
    assert primero.status_code == 201

    segundo = client.post("/combats", json=_reporte("clave-abc-123", rival.id))
    assert segundo.status_code == 200
    assert segundo.get_json()["id"] == primero.get_json()["id"]

    pendientes = client.get("/combats/pending").get_json()
    assert len([c for c in pendientes if c["reporter_id"] == jugador.id]) == 1


def test_un_reenvio_con_la_misma_clave_devuelve_el_combate_original(
    client, jugador, roles
):
    """Aunque cambie el cuerpo, la clave devuelve el combate ya creado."""
    rival = _usuario("beto@x.com", "Beto Ruiz")
    _login(client, jugador)

    primero = client.post("/combats", json=_reporte("clave-xyz", rival.id))
    assert primero.status_code == 201

    segundo = client.post(
        "/combats", json=_reporte("clave-xyz", rival.id, ganador=rival.id)
    )
    assert segundo.status_code == 200
    datos = segundo.get_json()
    assert datos["id"] == primero.get_json()["id"]
    # El resultado original no se modifica: el reenvío no tiene efectos.
    assert datos["status"] == "PENDIENTE"


def test_una_clave_demasiado_larga_se_rechaza(client, jugador, roles):
    rival = _usuario("beto@x.com", "Beto Ruiz")
    _login(client, jugador)
    r = client.post("/combats", json=_reporte("c" * 65, rival.id))
    assert r.status_code == 400
    assert "client_request_id" in r.get_json()["error"]


def test_la_clave_de_idempotencia_se_genera_antes_de_enviar(client):
    """El cliente genera la clave antes del envío y la reutiliza al encolar."""
    js = client.get("/static/js/reportar.js").get_data(as_text=True)
    assert "const clave = window.SASync ? window.SASync.nuevaClave() : null;" in js
    assert "client_request_id: clave" in js
    assert "encolarReporte(cuerpo, resumen, clave)" in js


def test_el_cliente_no_muestra_error_cuando_el_reporte_ya_existia(client):
    """Un 200 (reenvío) se informa como registro, no como error."""
    js = client.get("/static/js/reportar.js").get_data(as_text=True)
    assert "ya estaba registrado" in js
    sync = client.get("/static/js/sync.js").get_data(as_text=True)
    assert "yaRegistrado" in sync
    assert 'estado: "enviado"' in sync


def test_el_boton_de_envio_se_bloquea_durante_el_envio(client):
    js = client.get("/static/js/reportar.js").get_data(as_text=True)
    assert "boton.disabled = true" in js
    assert "boton.disabled = false" in js


# ---------------------------------------------------------------------------
# 9.4 — Listado de reportes pendientes de envío con estado por ítem
# ---------------------------------------------------------------------------


def test_la_vista_de_reportar_lista_los_reportes_guardados(client, jugador):
    _login(client, jugador)
    html = client.get("/reportar").get_data(as_text=True)
    assert 'id="lista-pendientes"' in html
    assert 'id="btn-reintentar"' in html
    assert 'id="btn-limpiar-enviados"' in html
    assert "Reportes pendientes de envío" in html


def test_la_lista_muestra_el_estado_de_cada_item(client):
    js = client.get("/static/js/reportar.js").get_data(as_text=True)
    assert "pintarPendientes" in js
    assert "etiqueta-pendiente" in js
    assert "etiqueta-enviado" in js
    assert "etiqueta-error" in js
    assert "Descartar" in js
    assert "Intentos:" in js


def test_la_lista_se_actualiza_al_cambiar_la_cola(client):
    js = client.get("/static/js/reportar.js").get_data(as_text=True)
    assert 'addEventListener("sa-outbox-cambio"' in js
    assert "cargarPendientes()" in js


def test_los_estilos_de_los_estados_existen(client):
    css = client.get("/static/css/estilos.css").get_data(as_text=True)
    assert ".etiqueta-enviado" in css
    assert ".etiqueta-error" in css
