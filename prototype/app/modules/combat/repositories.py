"""Persistencia de combates, participantes, confirmaciones y AuditLog.

Única capa del módulo que toca SQLAlchemy (regla transversal 4). Los servicios
trabajan contra esta interfaz y no conocen detalles de la sesión ni de la BD.

``ConfirmationRepository`` y ``AuditLogRepository`` se añaden en el Sprint 5
(tareas 5.1 y 5.3), junto a sus modelos.
"""

from app.extensions import db
from app.modules.combat.domain.estados import EstadoCombate
from app.modules.combat.models import Combat, CombatParticipant


class CombatRepository:
    """Acceso a datos del aggregate Combat."""

    @staticmethod
    def get_by_id(combat_id: int) -> Combat | None:
        """Devuelve el combate por id o None (con sus participantes cargados)."""
        return db.session.get(Combat, combat_id)

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
