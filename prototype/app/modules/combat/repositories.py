"""Persistencia de combates, participantes, confirmaciones y AuditLog.

Única capa del módulo que toca SQLAlchemy (regla transversal 4). Los servicios
trabajan contra esta interfaz y no conocen detalles de la sesión ni de la BD.

``ConfirmationRepository`` se añade en la tarea 5.2 y ``AuditLogRepository``
en la 5.3, junto a sus modelos.
"""

from app.extensions import db
from app.modules.combat.domain.estados import EstadoCombate
from app.modules.combat.models import (
    Combat,
    CombatParticipant,
    Confirmation,
)


class CombatRepository:
    """Acceso a datos del aggregate Combat."""

    @staticmethod
    def get_by_id(combat_id: int) -> Combat | None:
        """Devuelve el combate por id o None (con sus participantes cargados)."""
        return db.session.get(Combat, combat_id)

    @staticmethod
    def get_by_idempotency_key(
        community_id: int, reporter_id: int, client_request_id: str
    ) -> Combat | None:
        """Devuelve el combate ya reportado con esa clave de idempotencia o None."""
        return (
            db.session.execute(
                db.select(Combat).filter_by(
                    community_id=community_id,
                    reporter_id=reporter_id,
                    client_request_id=client_request_id,
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    def add(combat: Combat) -> Combat:
        """Persiste el aggregate (flush para disponer del id; commit fuera)."""
        db.session.add(combat)
        db.session.flush()
        return combat

    @staticmethod
    def pendientes_de_usuario(user_id: int, community_id: int) -> list[Combat]:
        """Combates PENDIENTEs donde ``user_id`` es participante o árbitro.

        La SQL ya deduplica (un usuario puede ser a la vez participante y
        árbitro) y ordena por fecha de juego para que la UI sea predecible.
        """
        consulta = (
            db.select(Combat)
            .where(
                Combat.community_id == community_id,
                Combat.status == EstadoCombate.PENDIENTE,
            )
            .outerjoin(CombatParticipant, CombatParticipant.combat_id == Combat.id)
            .where(
                db.or_(
                    CombatParticipant.user_id == user_id,
                    Combat.referee_id == user_id,
                )
            )
            .order_by(Combat.played_at.asc(), Combat.id.asc())
            .distinct()
        )
        return list(db.session.execute(consulta).scalars().all())

    @staticmethod
    def save() -> None:
        """Confirma la transacción en curso (Unit of Work del servicio llamante)."""
        db.session.commit()

    @staticmethod
    def rollback() -> None:
        """Revierte la transacción en curso ante error de dominio."""
        db.session.rollback()


class CombatParticipantRepository:
    """Consultas auxiliares sobre los participantes de un combate."""

    @staticmethod
    def participantes_de(combat_id: int) -> list[CombatParticipant]:
        """Participantes de un combate en orden de declaración."""
        return list(
            db.session.execute(
                db.select(CombatParticipant)
                .where(CombatParticipant.combat_id == combat_id)
                .order_by(CombatParticipant.id)
            )
            .scalars()
            .all()
        )


class ConfirmationRepository:
    """Acceso a datos de las confirmaciones de un combate."""

    @staticmethod
    def get(combat_id: int, user_id: int) -> Confirmation | None:
        """Devuelve la confirmación de ese usuario en ese combate o None."""
        return db.session.execute(
            db.select(Confirmation).filter_by(combat_id=combat_id, user_id=user_id)
        ).scalars().first()

    @staticmethod
    def confirmaciones_de(combat_id: int) -> list[Confirmation]:
        """Todas las confirmaciones del combate en orden de llegada."""
        return list(
            db.session.execute(
                db.select(Confirmation)
                .where(Confirmation.combat_id == combat_id)
                .order_by(Confirmation.id)
            )
            .scalars()
            .all()
        )

    @staticmethod
    def add(confirmation: Confirmation) -> Confirmation:
        """Persiste la confirmación (flush para disponer del id)."""
        db.session.add(confirmation)
        db.session.flush()
        return confirmation

    @staticmethod
    def save() -> None:
        """Confirma la transacción en curso (Unit of Work del servicio llamante)."""
        db.session.commit()
