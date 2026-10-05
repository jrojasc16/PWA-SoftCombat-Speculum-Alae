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
from app.shared.errors import AuthError, ConflictError, DomainError

# Política de contraseñas del MVP (documentar en manual de usuario, Sprint 13).
PASSWORD_MIN_LENGTH = 8

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
