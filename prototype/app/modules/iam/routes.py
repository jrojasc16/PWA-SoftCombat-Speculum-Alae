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
from app.shared.decorators import api_login_required, role_required
from app.shared.errors import AuthError, DomainError
from app.shared.http import payload_json_o_formulario

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


@bp.get("/me/community")
@api_login_required
def mi_comunidad():
    """Directorio de mi comunidad para los formularios de la PWA (RF6/RF8).

    Devuelve mi usuario (``yo``), los demás ``jugadores`` y los ``arbitros``
    con **solo** id, nombre y rol: el formulario de reportar resuelve así
    nombre → id sin publicar correos. Pide sesión (401 en caso contrario).
    """
    return jsonify(services.comunidad_de(current_user)), 200


@bp.get("/admin/users")
@api_login_required
@role_required("admin", "super_admin")
def listar_usuarios_admin():
    """Usuarios de mi comunidad para el panel de administración (UC10).

    - ``200``: lista de usuarios (incluye los desactivados).
    - ``401``: sin sesión. ``403``: rol insuficiente.
    """
    incluir_inactivos = request.args.get("incluir_inactivos", "1") != "0"
    usuarios = services.listar_usuarios_para_admin(current_user.id, incluir_inactivos)
    return jsonify(usuarios), 200


@bp.route("/admin/users/<int:user_id>", methods=["PATCH", "POST"])
@api_login_required
@role_required("admin", "super_admin")
def actualizar_usuario_admin(user_id: int):
    """Activa/desactiva una cuenta o le cambia el rol (UC10/UC11).

    Acepta ``PATCH`` (API/PWA) y ``POST`` (formulario web, que no puede enviar
    PATCH por sí mismo). Campos admitidos: ``active`` (booleano) y ``role``
    (nombre del rol). Los campos que empiezan por ``_`` (metadatos del
    formulario) se ignoran.
    """
    data = {
        campo: valor
        for campo, valor in payload_json_o_formulario().items()
        if not campo.startswith("_")
    }
    admin_id = current_user.id
    if "active" in data:
        usuario = services.cambiar_estado_usuario(
            admin_id, user_id, _booleano(data["active"])
        )
    elif "role" in data:
        usuario = services.cambiar_rol_usuario(admin_id, user_id, data["role"])
    else:
        raise DomainError(
            "Indica 'active' para activar/desactivar la cuenta o 'role' para "
            "cambiar el rol del usuario."
        )
    return jsonify(usuario), 200


def _booleano(valor) -> bool:
    """Interpreta un valor de formulario o JSON como booleano.

    Acepta ``True``/``False`` (JSON), ``"true"/"false"``, ``"1"/"0"`` y
    ``"on"/"off"`` (lo que manda un ``<input type="checkbox">``).
    """
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in ("true", "1", "on", "yes", "sí"):
        return True
    if texto in ("false", "0", "off", "no"):
        return False
    raise DomainError("El campo 'active' debe ser un valor booleano.")
