"""Tests del módulo IAM (Sprint 2.8).

Cubre: registro exitoso, email duplicado (case-insensitive), validación de
email/contraseña/nombre, hash bcrypt con costo 12 efectivo (RNF001), login
correcto/incorrecto, cuenta desactivada, cierre de sesión y acceso protegido
por ``@role_required`` permitido/denegado según rol.
"""

import pytest

from app.extensions import db
from app.modules.iam import services
from app.modules.iam.models import Role, User
from app.modules.iam.repositories import RoleRepository
from app.shared.decorators import role_required
from app.shared.errors import AuthError, ConflictError, DomainError

VALIDO = {"email": "ana@x.com", "password": "password123", "name": "Ana Rojas"}


@pytest.fixture
def admin_route(app):
    """Ruta de prueba protegida con @role_required('admin', 'super_admin')."""

    @app.get("/admin/demo")
    @role_required("admin", "super_admin")
    def _demo():
        return {"ok": True}

    return app


# ---------- Registro ----------


def test_registro_exitoso(roles):
    """Registro: usuario con rol jugador, email normalizado y hash bcrypt."""
    user = services.register_user(**VALIDO)
    assert user.id is not None
    assert user.email == "ana@x.com"
    assert user.role_id == roles["jugador"].id
    assert user.active is True
    assert user.password_hash != VALIDO["password"]


def test_email_duplicado_rechazado(roles):
    """Duplicado (incluso con mayúsculas distintas) → ConflictError."""
    services.register_user(**VALIDO)
    with pytest.raises(ConflictError):
        services.register_user(email="ANA@X.COM", password="password123", name="Otra")


@pytest.mark.parametrize(
    "campo",
    [
        {"email": "sin-arroba"},
        {"email": "sin@dominio"},
        {"password": "corta"},
        {"password": ""},
        {"name": "A"},
        {"name": ""},
    ],
)
def test_registro_validaciones(roles, campo):
    """Email mal formado, contraseña <8 y nombre <2 → DomainError."""
    datos = {**VALIDO, **campo}
    with pytest.raises(DomainError):
        services.register_user(**datos)


def test_hash_bcrypt_costo_12_efectivo(app, roles):
    """RNF001: fuera de tests el hash se genera con costo 12.

    TestingConfig usa costo 4 por velocidad; aquí se comprueba que la
    configuración base y de producción fijan 12 y que el hash es verificable.
    """
    from app.config import Config, ProductionConfig

    assert Config.BCRYPT_LOG_ROUNDS == 12
    assert ProductionConfig.BCRYPT_LOG_ROUNDS == 12

    user = services.register_user(**VALIDO)
    assert user.password_hash.startswith("$2b$04$")  # costo reducido SOLO en tests
    from app.extensions import bcrypt

    assert bcrypt.check_password_hash(user.password_hash, VALIDO["password"])


# ---------- Autenticación ----------


def test_login_correcto(roles):
    """authenticate devuelve el usuario con credenciales válidas."""
    creado = services.register_user(**VALIDO)
    autenticado = services.authenticate(VALIDO["email"], VALIDO["password"])
    assert autenticado.id == creado.id


def test_login_incorrecto_mensaje_generico(roles):
    """Email inexistente y contraseña mala dan EL MISMO error (sin oráculo)."""
    services.register_user(**VALIDO)
    for email, pw in [("nadie@x.com", "password123"), (VALIDO["email"], "mala"), (None, None)]:
        with pytest.raises(AuthError, match="Credenciales inválidas."):
            services.authenticate(email, pw)


def test_cuenta_desactivada_no_autentica(roles):
    """Un usuario con active=False no puede iniciar sesión."""
    user = services.register_user(**VALIDO)
    user.active = False
    db.session.commit()
    with pytest.raises(AuthError):
        services.authenticate(VALIDO["email"], VALIDO["password"])


# ---------- Rutas y control de acceso ----------


def test_flujo_completo_register_login_protegido_logout(client, admin_route, roles):
    """register → sesión → ruta admin denegada (403) → logout → 401.

    Con rol admin: register/login → ruta admin permitida (200).
    """
    # Jugador: registro + sesión + 403 en ruta admin + logout + 401
    r = client.post("/auth/register", json=VALIDO)
    assert r.status_code == 201 and r.get_json()["role"] == "jugador"
    assert client.get("/me").status_code == 200
    assert client.get("/admin/demo").status_code == 403
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/me").status_code == 401

    # Admin: login (también acepta formulario) + 200 en ruta admin
    admin = services.register_user(email="admin@x.com", password="password123", name="Admin")
    admin.role_id = RoleRepository.get_by_name("admin").id
    db.session.commit()
    r = client.post("/auth/login", data={"email": "admin@x.com", "password": "password123"})
    assert r.status_code == 200
    r = client.get("/admin/demo")
    assert r.status_code == 200 and r.get_json() == {"ok": True}


def test_login_api_credenciales_malas(client, roles):
    """La API responde 401 con mensaje genérico ante credenciales inválidas."""
    services.register_user(**VALIDO)
    r = client.post("/auth/login", json={"email": VALIDO["email"], "password": "mala"})
    assert r.status_code == 401
    assert r.get_json() == {"error": "Credenciales inválidas."}
