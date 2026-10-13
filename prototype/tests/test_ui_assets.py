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
