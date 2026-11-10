"""Servicios del módulo IAM: registro y autenticación de usuarios.

Reglas de negocio (plan Sprint 2.4):
- Email con formato válido, único en el sistema (normalizado a minúsculas).
- Contraseña mínima de 8 caracteres; hash con bcrypt costo 12 (RNF001; el
  costo real lo fija la configuración de la app).
- El rol por defecto del registro es ``jugador``.
- Autenticación con mensaje genérico ante fallo (no revela si el email existe).
"""

import re

from flask import current_app

from app.extensions import bcrypt
from app.modules.iam.models import User
from app.modules.iam.repositories import RoleRepository, UserRepository
from app.shared.errors import (
    AuthError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
)

# Política de contraseñas del MVP (documentar en manual de usuario, Sprint 13).
PASSWORD_MIN_LENGTH = 8

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Roles que administran la comunidad (RBAC del panel, Sprint 10.2).
ROLES_ADMIN = frozenset({"admin", "super_admin"})

# Rol que solo puede conceder o revocar un ``super_admin``.
ROL_SUPER_ADMIN = "super_admin"


def register_user(email: str, password: str, name: str, community_id: int = 1) -> User:
    """Registra un usuario nuevo con rol ``jugador`` y lo devuelve persistido.

    Lanza:
        DomainError: email con formato inválido, contraseña débil o nombre vacío.
        ConflictError: email ya registrado.
    """
    email = (email or "").strip().lower()
    name = (name or "").strip()

    if not _EMAIL_RE.match(email):
        raise DomainError("El correo electrónico no tiene un formato válido.")
    if len(name) < 2:
        raise DomainError("El nombre debe tener al menos 2 caracteres.")
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        raise DomainError(
            f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres."
        )

    if UserRepository.get_by_email(email) is not None:
        raise ConflictError("Ya existe una cuenta registrada con ese correo.")

    role = RoleRepository.get_by_name("jugador")
    if role is None:  # protección: el seed de roles debe haber corrido
        raise DomainError("Configuración incompleta: no existe el rol 'jugador'.")

    password_hash = bcrypt.generate_password_hash(
        password, rounds=current_app.config["BCRYPT_LOG_ROUNDS"]
    ).decode("utf-8")

    user = User(
        email=email,
        password_hash=password_hash,
        name=name,
        role_id=role.id,
        community_id=community_id,
        active=True,
    )
    UserRepository.add(user)
    UserRepository.save()
    return user


def authenticate(email: str, password: str) -> User:
    """Autentica por email/contraseña y devuelve el usuario.

    Mensaje genérico ante cualquier fallo (no oráculo de emails) y rechazo de
    cuentas desactivadas. Lanza AuthError en todos los casos de error.
    """
    user = UserRepository.get_by_email((email or "").strip().lower())
    if (
        user is None
        or not bcrypt.check_password_hash(user.password_hash, password or "")
        or not user.active
    ):
        raise AuthError("Credenciales inválidas.")
    return user


# Roles que pueden actuar como árbitro en un reporte (mismos que en combate;
# se declaran aquí para no crear una dependencia iam → combat).
ROLES_ARBITRO = frozenset({"arbitro", "admin", "super_admin"})


def comunidad_de(usuario: User) -> dict:
    """Directorio mínimo de la comunidad para los formularios web (RF6/RF8).

    El formulario de reporte necesita resolver **nombre → id** del oponente y
    del árbitro sin que el jugador tenga que escribir identificadores a mano.

    Solo expone id, nombre y rol: nunca correos ni hashes (RNF de datos
    públicos). Los usuarios desactivados no aparecen.
    """
    miembros = UserRepository.listar_por_comunidad(usuario.community_id)
    return {
        "community_id": usuario.community_id,
        "yo": {"id": usuario.id, "name": usuario.name},
        "jugadores": [
            {"id": u.id, "name": u.name} for u in miembros if u.id != usuario.id
        ],
        "arbitros": [
            {"id": u.id, "name": u.name}
            for u in miembros
            if u.role.name in ROLES_ARBITRO
        ],
    }


# ---------------------------------------------------------------------------
# Gestión de usuarios desde el panel de administración (Sprint 10.2)
# ---------------------------------------------------------------------------


def _admin_de(admin_id) -> User:
    """Resuelve el administrador que ejecuta la acción y valida su rol.

    Raises:
        NotFoundError: el usuario administrador no existe (404).
        ForbiddenError: no tiene rol de administración (403).
    """
    try:
        identificador = int(admin_id)
    except (TypeError, ValueError) as exc:
        raise DomainError("El identificador del administrador no es válido.") from exc
    admin = UserRepository.get_by_id(identificador)
    if admin is None:
        raise NotFoundError(f"No existe el usuario {identificador}.")
    if admin.role.name not in ROLES_ADMIN:
        raise ForbiddenError("No tienes permisos para esta acción.")
    return admin


def _objetivo(admin: User, user_id) -> User:
    """Resuelve el usuario objetivo de la acción dentro de la comunidad del admin.

    Aplica el aislamiento por ``community_id`` (RNF006): un admin nunca puede
    tocar cuentas de otra comunidad.
    """
    try:
        identificador = int(user_id)
    except (TypeError, ValueError) as exc:
        raise DomainError("El identificador de usuario no es válido.") from exc
    objetivo = UserRepository.get_by_id(identificador)
    if objetivo is None:
        raise NotFoundError(f"No existe el usuario {identificador}.")
    if objetivo.community_id != admin.community_id:
        raise ForbiddenError("No tienes permisos para gestionar usuarios de otra comunidad.")
    return objetivo


def _dto_usuario(usuario: User) -> dict:
    """Proyección de un usuario para el panel (incluye el correo: es privado)."""
    return {
        "id": usuario.id,
        "name": usuario.name,
        "email": usuario.email,
        "role": usuario.role.name,
        "active": usuario.active,
        "community_id": usuario.community_id,
    }


def listar_usuarios_para_admin(admin_id, incluir_inactivos: bool = True) -> list[dict]:
    """Lista los usuarios de la comunidad del administrador (panel de administración).

    Por defecto incluye las cuentas desactivadas para que el admin pueda
    reactivarlas (UC10: gestionar usuarios).

    Raises:
        NotFoundError: el administrador no existe (404).
        ForbiddenError: el solicitante no es admin/super_admin (403).
    """
    admin = _admin_de(admin_id)
    usuarios = UserRepository.listar_por_comunidad(
        admin.community_id, incluir_inactivos=incluir_inactivos
    )
    return [_dto_usuario(u) for u in usuarios]


def cambiar_estado_usuario(admin_id, user_id, activo: bool) -> dict:
    """Activa o desactiva una cuenta de la comunidad (UC10).

    Reglas de dominio:

    - Solo ``admin``/``super_admin`` (403 para el resto).
    - Solo cuentas de la **misma comunidad** (RNF006).
    - Un administrador no puede desactivar **su propia** cuenta: se quedaría
      sin acceso al panel y sin nadie que lo pueda reactivar.

    Raises:
        NotFoundError: administrador o usuario objetivo inexistente (404).
        ForbiddenError: rol insuficiente, otra comunidad o auto-desactivación (403).
        DomainError: valor de ``activo`` inválido (400).
    """
    admin = _admin_de(admin_id)
    if not isinstance(activo, bool):
        raise DomainError("'activo' debe ser un valor booleano.")
    objetivo = _objetivo(admin, user_id)
    if not activo and objetivo.id == admin.id:
        raise ForbiddenError("No puedes desactivar tu propia cuenta.")
    objetivo.active = activo
    UserRepository.save()
    return _dto_usuario(objetivo)


def cambiar_rol_usuario(admin_id, user_id, rol: str) -> dict:
    """Cambia el rol de una cuenta de la comunidad (UC11).

    Reglas de dominio:

    - Solo ``admin``/``super_admin`` (403 para el resto).
    - Solo cuentas de la **misma comunidad** (RNF006).
    - El rol destino debe existir en la tabla ``roles``.
    - Solo un ``super_admin`` puede conceder o quitar el rol ``super_admin``
      (evita el escalamiento de privilegios desde un ``admin``).
    - Un administrador no puede cambiar **su propio** rol.

    Raises:
        NotFoundError: administrador o usuario objetivo inexistente (404).
        ForbiddenError: rol insuficiente, otra comunidad, auto-cambio o
            escalamiento a ``super_admin`` (403).
        DomainError: rol inexistente (400).
    """
    admin = _admin_de(admin_id)
    nombre_rol = (rol or "").strip()
    if not nombre_rol:
        raise DomainError("El rol es obligatorio.")
    rol_destino = RoleRepository.get_by_name(nombre_rol)
    if rol_destino is None:
        raise DomainError(f"El rol '{nombre_rol}' no existe.")
    objetivo = _objetivo(admin, user_id)
    if objetivo.id == admin.id:
        raise ForbiddenError("No puedes cambiar tu propio rol.")
    if rol_destino.name == ROL_SUPER_ADMIN and admin.role.name != ROL_SUPER_ADMIN:
        raise ForbiddenError(
            "Solo un super administrador puede asignar el rol super_admin."
        )
    objetivo.role_id = rol_destino.id
    UserRepository.save()
    return _dto_usuario(objetivo)
