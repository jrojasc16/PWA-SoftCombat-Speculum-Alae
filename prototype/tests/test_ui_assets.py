"""Tests de los estáticos del cliente (Sprint 7.6): JS por vista, PWA y SW.

Son pruebas de contrato de contenido: confirman que las páginas referencian
sus scripts, que el manifest está enlazado y que el service worker existe y
protege los recursos de sesión en su política de caché.
"""

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
def usuario(roles):
    return _usuario("ana@x.com", "Ana Rojas")


def _login(client, usuario):
    r = client.post(
        "/auth/login", json={"email": usuario.email, "password": "password123"}
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Scripts enlazados por vista
# ---------------------------------------------------------------------------


def test_base_enlaza_manifest_y_script_comun(client, usuario):
    html = client.get("/").get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert "manifest.json" in html
    assert 'name="theme-color"' in html
    assert "js/app.js" in html


def test_reportar_enlaza_su_script(client, usuario):
    _login(client, usuario)
    html = client.get("/reportar").get_data(as_text=True)
    assert "js/reportar.js" in html
    assert "js/app.js" in html  # también el común


def test_pendientes_enlaza_su_script(client, usuario):
    _login(client, usuario)
    html = client.get("/pendientes").get_data(as_text=True)
    assert "js/pendientes.js" in html


# ---------------------------------------------------------------------------
# Estáticos servidos
# ---------------------------------------------------------------------------


def test_estaticos_js_se_sirven(client):
    for ruta in (
        "/static/js/app.js",
        "/static/js/reportar.js",
        "/static/js/pendientes.js",
        "/static/sw.js",
        "/static/db.js",
    ):
        r = client.get(ruta)
        assert r.status_code == 200, ruta
        assert "javascript" in r.content_type


def test_sw_permite_scope_raiz(client):
    """Sin Service-Worker-Allowed el SW solo controlaría /static/."""
    r = client.get("/static/sw.js")
    assert r.headers.get("Service-Worker-Allowed") == "/"


def test_manifest_es_json_valido(client):
    r = client.get("/static/manifest.json")
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["start_url"] == "/ranking"
    assert datos["display"] == "standalone"


def test_manifest_tiene_los_campos_de_instalabilidad(client):
    """Criterios de instalabilidad de una PWA (tarea 8.1)."""
    datos = client.get("/static/manifest.json").get_json()
    assert datos["name"]
    assert datos["short_name"]
    assert datos["start_url"].startswith("/")
    assert datos["scope"] == "/"
    assert datos["display"] == "standalone"
    assert datos["theme_color"].startswith("#")
    assert datos["background_color"].startswith("#")
    assert datos["lang"] == "es"


def test_manifest_declara_iconos_192_y_512(client):
    datos = client.get("/static/manifest.json").get_json()
    tamanos = {icono["sizes"] for icono in datos["icons"]}
    assert {"192x192", "512x512"} <= tamanos
    for icono in datos["icons"]:
        assert icono["type"] == "image/png"
        assert "maskable" in icono["purpose"]


def test_iconos_png_se_sirven_con_las_dimensiones_declaradas(client):
    manifest = client.get("/static/manifest.json").get_json()
    for icono in manifest["icons"]:
        r = client.get(icono["src"])
        assert r.status_code == 200
        assert r.content_type == "image/png"
        datos = r.get_data()
        # Firma PNG (8 bytes) + IHDR con ancho y alto en big-endian.
        assert datos[:8] == b"\x89PNG\r\n\x1a\n"
        ancho = int.from_bytes(datos[16:20], "big")
        alto = int.from_bytes(datos[20:24], "big")
        lado = int(icono["sizes"].split("x")[0])
        assert (ancho, alto) == (lado, lado)


def test_css_responsive_define_media_queries(client):
    css = client.get("/static/css/estilos.css").get_data(as_text=True)
    # Mobile-first con punto de corte a 720px (RNF003: usable en móvil).
    assert "@media (min-width: 720px)" in css
    assert ".nav-toggle" in css


# ---------------------------------------------------------------------------
# Service worker: app-shell con caché pero sin tocar la sesión
# ---------------------------------------------------------------------------


def test_sw_no_cachea_recursos_de_sesion(client):
    sw = client.get("/static/sw.js").get_data(as_text=True)
    # Excluye explícitamente pendientes/historial/combats (datos por sesión).
    for ruta_sensible in ('"/me"', '"/combats"', '"/admin"', '"/auth"'):
        assert ruta_sensible in sw
    # Solo responde a peticiones GET.
    assert 'peticion.method !== "GET"' in sw


def test_sw_precachea_app_shell(client):
    sw = client.get("/static/sw.js").get_data(as_text=True)
    assert '"/ranking"' in sw
    assert '"/static/css/estilos.css"' in sw


# ---------------------------------------------------------------------------
# Service worker: runtime cache stale-while-revalidate con marca de tiempo
# ---------------------------------------------------------------------------


def test_sw_cachea_ranking_e_historial_con_stale_while_revalidate(client):
    sw = client.get("/static/sw.js").get_data(as_text=True)
    assert '"/api/ranking"' in sw
    assert '"/me/history"' in sw
    assert "responderConSWR" in sw
    # La copia cacheada se devuelve de inmediato y la red se revalida detrás.
    assert "guardada" in sw and "desdeRed" in sw


def test_sw_marca_el_tiempo_de_las_copias_cacheadas(client):
    sw = client.get("/static/sw.js").get_data(as_text=True)
    assert "X-SW-Cache-Time" in sw
    assert "new Date().toISOString()" in sw


def test_sw_permite_consultar_y_purgar_la_cache_desde_la_ui(client):
    sw = client.get("/static/sw.js").get_data(as_text=True)
    assert "sa-estado-cache" in sw
    assert "sa-limpiar-cache" in sw
    # Al cerrar sesión se borran las lecturas propias cacheadas.
    assert 'pathname.startsWith("/me")' in sw


def test_sw_ignora_el_ranking_en_la_estrategia_de_red_primero(client):
    """El ranking usa SWR; no debe quedar en la rama network-first."""
    sw = client.get("/static/sw.js").get_data(as_text=True)
    rama_red = sw.split("Navegaciones y estáticos")[1]
    assert 'url.pathname === "/api/ranking"' not in rama_red


# ---------------------------------------------------------------------------
# Indicador de modo offline y marca de tiempo de los datos (tarea 8.3)
# ---------------------------------------------------------------------------


def test_layout_incluye_aviso_offline_y_marca_de_datos(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="aviso-offline"' in html
    assert 'id="marca-datos"' in html
    assert 'role="status"' in html


def test_js_comun_registra_el_sw_y_gestiona_el_estado_de_red(client):
    js = client.get("/static/js/app.js").get_data(as_text=True)
    assert 'register("/static/sw.js")' in js
    assert 'addEventListener("online"' in js
    assert 'addEventListener("offline"' in js
    assert "X-SW-Cache-Time" in js
    assert "Datos de las " in js


def test_js_comun_purga_la_cache_al_cerrar_sesion(client, usuario):
    _login(client, usuario)
    html = client.get("/").get_data(as_text=True)
    assert 'id="enlace-salir"' in html
    js = client.get("/static/js/app.js").get_data(as_text=True)
    assert "sa-limpiar-cache" in js


def test_pagina_offline_responde_y_pinta_las_copias_guardadas(client):
    r = client.get("/offline")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "js/offline.js" in html
    assert 'id="ranking-offline"' in html
    assert 'id="historial-offline"' in html


def test_sw_sirve_la_pagina_offline_y_entrega_los_datos_cacheados(client):
    sw = client.get("/static/sw.js").get_data(as_text=True)
    assert '"/offline"' in sw
    assert "sa-datos-cache" in sw
    js = client.get("/static/js/offline.js").get_data(as_text=True)
    assert "sa-datos-cache" in js
