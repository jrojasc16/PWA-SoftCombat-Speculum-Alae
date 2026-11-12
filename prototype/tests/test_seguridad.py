"""Revisión de seguridad (Sprint 12.6): RNF001 y datos públicos.

Verifica los cuatro puntos del plan:

1. bcrypt con **costo 12 efectivo** (no solo configurado) al registrar.
2. Cookies de sesión con **HttpOnly** y **SameSite=Lax**; `Secure` activo
   en producción.
3. **HTTPS forzado en producción**: `SECRET_KEY` obligatoria, debug apagado,
   `Secure` en cookies y redirección 308 cuando el proxy reporta HTTP
   (sin bucles: solo con evidencia positiva `X-Forwarded-Proto: http`).
4. **Sin datos sensibles en respuestas públicas**: `/health`, `/api/ranking`
   y `/me/community` exponen solo sus campos autorizados, y los errores de
   dominio son `{"error": ...}` sin trazas.

El informe completo (evidencia `file:line` y conclusiones) está en
``documentation/REVISION_SEGURIDAD.md``.
"""

import pytest

from app import create_app
from app.config import Config, ProductionConfig


# ---------------------------------------------------------------------------
# 1. bcrypt costo 12 efectivo (RNF001)
# ---------------------------------------------------------------------------


def test_bcrypt_costo_12_efectivo_al_registrar(app, roles):
    """El hash real que genera el servicio usa $2b$12$ y es verificable.

    TestingConfig fija costo 4 por velocidad; aquí se pisa a 12 (como en el
    despliegue) para comprobar el camino completo: servicio → bcrypt → BD.
    """
    from app.extensions import bcrypt
    from app.modules.iam import services

    app.config["BCRYPT_LOG_ROUNDS"] = 12

    user = services.register_user(
        email="ana@x.com", password="password123", name="Ana Rojas"
    )

    assert user.password_hash.startswith("$2b$12$")
    assert user.password_hash != "password123"
    assert bcrypt.check_password_hash(user.password_hash, "password123")
    assert not bcrypt.check_password_hash(user.password_hash, "otra-password")


# ---------------------------------------------------------------------------
# 2. Cookies de sesión: HttpOnly + SameSite (Secure en producción)
# ---------------------------------------------------------------------------


def test_cookie_de_sesion_httponly_y_samesite(client, roles):
    """El login devuelve la cookie de sesión con HttpOnly y SameSite=Lax."""
    r = client.post(
        "/auth/register",
        json={"email": "ana@x.com", "password": "password123", "name": "Ana Rojas"},
    )
    assert r.status_code == 201

    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie  # inaccesible desde JavaScript (anti-XSS)
    assert "SameSite=Lax" in cookie  # mitiga CSRF en POST cross-site
    # Secure NO aparece en pruebas: TestingConfig corre por http.
    # Se activa en producción (siguiente test de configuración).
    assert "Secure" not in cookie


def test_config_produccion_cookies_seguras():
    """ProductionConfig: Secure + HttpOnly + SameSite; base solo HTTPONLY/Lax."""
    assert ProductionConfig.SESSION_COOKIE_SECURE is True
    assert ProductionConfig.SESSION_COOKIE_HTTPONLY is True
    assert ProductionConfig.SESSION_COOKIE_SAMESITE == "Lax"
    assert ProductionConfig.BCRYPT_LOG_ROUNDS == 12

    assert Config.SESSION_COOKIE_HTTPONLY is True
    assert Config.SESSION_COOKIE_SAMESITE == "Lax"
    assert Config.SESSION_COOKIE_SECURE is False  # dev/testing por http


# ---------------------------------------------------------------------------
# 3. HTTPS forzado en producción (SECRET_KEY, debug, redirección tras proxy)
# ---------------------------------------------------------------------------


def test_produccion_sin_secret_key_no_arranca(monkeypatch):
    """Sin SECRET_KEY del entorno, la app de producción no arranca."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")


def test_produccion_con_secret_key_arranca_segura(monkeypatch):
    """Con SECRET_KEY: clave real cargada, cookies Secure y debug apagado."""
    monkeypatch.setenv("SECRET_KEY", "clave-secreta-de-prueba-123456")
    app = create_app("production")

    assert app.config["SECRET_KEY"] == "clave-secreta-de-prueba-123456"
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.debug is False  # sin trazas ni entorno de depuración
    assert app.config["TESTING"] is False


def test_https_forzado_tras_proxy_sin_bucle(monkeypatch):
    """RNF001: redirección 308 solo con X-Forwarded-Proto: http.

    - Proxy reporta http → 308 a https (308 preserva método y cuerpo,
      necesario para los POST de la cola offline).
    - Proxy reporta https → 200 directo.
    - Sin cabecera (conexión directa o plataforma sin proxy) → 200:
      así no puede existir bucle de redirección; ese caso lo cubre el
      toggle «Force HTTPS» de PythonAnywhere (despliegue, tarea 13.2).
    """
    monkeypatch.setenv("SECRET_KEY", "clave-secreta-de-prueba-123456")
    app = create_app("production")
    c = app.test_client()

    r = c.get("/", headers={"X-Forwarded-Proto": "http"})
    assert r.status_code == 308
    assert r.headers["Location"] == "https://localhost/"

    r = c.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200

    r = c.get("/health")
    assert r.status_code == 200

    # Un POST conserva método y cuerpo con 308 (nunca degrada a GET).
    r = c.post(
        "/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"X-Forwarded-Proto": "http"},
    )
    assert r.status_code == 308
    assert r.headers["Location"] == "https://localhost/auth/login"


# ---------------------------------------------------------------------------
# 4. Sin datos sensibles en respuestas públicas
# ---------------------------------------------------------------------------


def test_health_expone_solo_estado_y_entorno(client):
    """/health no filtra configuración (ni claves ni rutas internas)."""
    r = client.get("/health")
    assert r.status_code == 200
    assert set(r.get_json()) == {"status", "env"}


def test_api_ranking_contrato_sin_campos_extra(client):
    """El contrato público es cerrado: nada fuera de community/page/items."""
    r = client.get("/api/ranking")
    assert set(r.get_json()) == {"community_id", "page", "per_page", "total", "items"}

    # Error de validación: solo {"error"}, sin traza ni detalles internos.
    r = client.get("/api/ranking?per_page=0")
    assert r.status_code == 400
    assert set(r.get_json()) == {"error"}


def test_directorio_comunidad_sin_correos_ni_hashes(client, roles):
    """GET /me/community (dirige el formulario offline) sin correos ni hashes."""
    r = client.post(
        "/auth/register",
        json={"email": "ana@x.com", "password": "password123", "name": "Ana Rojas"},
    )
    assert r.status_code == 201

    r = client.get("/me/community")
    assert r.status_code == 200
    cuerpo = r.get_data(as_text=True)
    assert "@" not in cuerpo
    assert "password" not in cuerpo
    assert "$2b$" not in cuerpo
