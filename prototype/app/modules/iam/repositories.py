"""Repositorio de usuarios y roles del módulo IAM.

Única capa del módulo que toca SQLAlchemy (regla transversal 4). Los servicios
trabajan contra esta interfaz y no conocen detalles de la sesión ni de la BD.
"""

from app.extensions import db
from app.modules.iam.models import Role, User


class UserRepository:
    """Acceso a datos de User."""

    @staticmethod
    def get_by_id(user_id: int) -> User | None:
        """Devuelve el usuario por su id o None."""
        return db.session.get(User, user_id)

    @staticmethod
    def get_by_email(email: str) -> User | None:
        """Devuelve el usuario por email (normalizado a minúsculas) o None."""
        return (
            db.session.execute(
                db.select(User).filter_by(email=email.strip().lower())
            )
            .scalars()
            .first()
        )

    @staticmethod
    def add(user: User) -> User:
        """Persiste un usuario nuevo (flush para disponer del id; commit fuera).

        El email se normaliza a minúsculas al guardar para mantener la
        consistencia con la búsqueda (``get_by_email``).
        """
        user.email = user.email.strip().lower()
        db.session.add(user)
        db.session.flush()
        return user

    @staticmethod
    def save() -> None:
        """Confirma la transacción en curso (Unit of Work del servicio llamante)."""
        db.session.commit()

    @staticmethod
    def rollback() -> None:
        """Revierte la transacción en curso ante error de dominio."""
        db.session.rollback()


class RoleRepository:
    """Acceso a datos de Role."""

    @staticmethod
    def get_by_name(name: str) -> Role | None:
        """Devuelve el rol por nombre o None."""
        return (
            db.session.execute(db.select(Role).filter_by(name=name))
            .scalars()
            .first()
        )
