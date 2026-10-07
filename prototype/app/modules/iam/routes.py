"""Blueprint iam: endpoints de registro, login, logout, usuarios y roles.

Las entradas de los métodos post y get son JSON (enviadas por el body de la petición) o formulario web (enviado por el navegador).
Las salidas son JSON.

Las rutas solo adaptan HTTP ↔ servicios (regla transversal 4): parsean la
petición, llaman a ``services`` y serializan la respuesta. Los errores de
dominio se propagan al manejador global (tarea 2.7).
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import login_manager
from app.modules.iam import services
from app.modules.iam.repositories import UserRepository
from app.shared.errors import AuthError

bp = Blueprint("iam", __name__)

# Endpoints bajo /auth según el plan (Sprint 2.5).
_URL_PREFIX = "/auth"


@login_manager.user_loader
def load_user(user_id: str):
    """Cargador de sesión de Flask-Login: reconstruye el usuario por id."""
    return UserRepository.get_by_id(int(user_id))


def _payload() -> dict:
    """Cuerpo de la petición (JSON o formulario web)."""
    return request.get_json(silent=True) or request.form.to_dict()


def _user_json(user) -> dict:
    """Proyección pública del usuario autenticado (sin datos sensibles)."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role.name,
        "community_id": user.community_id,
    }


@bp.post(f"{_URL_PREFIX}/register")
def register():
    """Registra un jugador nuevo e inicia su sesión (flujo en 1 paso de la UI)."""
    data = _payload()
    user = services.register_user(
        email=data.get("email", ""),
        password=data.get("password", ""),
        name=data.get("name", ""),
    )
    login_user(user)
    return jsonify(_user_json(user)), 201


@bp.post(f"{_URL_PREFIX}/login")
def login():
    """Inicia sesión con email/contraseña (cookie de sesión HttpOnly)."""
    data = _payload()
    user = services.authenticate(
        email=data.get("email", ""), password=data.get("password", "")
    )
    login_user(user)
    return jsonify(_user_json(user)), 200


@bp.post(f"{_URL_PREFIX}/logout")
@login_required
def logout():
    """Cierra la sesión actual."""
    logout_user()
    return jsonify({"message": "Sesión cerrada."}), 200


@bp.get("/me")
def me():
    """Perfil del usuario autenticado (401 si no hay sesión)."""
    if not current_user.is_authenticated:
        raise AuthError("Autenticación requerida.")
    return jsonify(_user_json(current_user)), 200
