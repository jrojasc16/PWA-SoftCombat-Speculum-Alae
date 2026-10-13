"""Consultas indexadas por user_id.

Única capa del módulo history que toca SQLAlchemy (regla transversal 4).
Combina tres fuentes ya existentes: los combates en los que participo
(``combat``), el snapshot de mi índice en cada uno (``ranking``) y el nombre
del rival (``iam``), sin crear tablas nuevas.
"""

from sqlalchemy.orm import selectinload

from app.extensions import db
from app.modules.combat.models import Combat, CombatParticipant
from app.modules.ranking.models import RatingHistory


class HistorialRepository:
    """Acceso al historial de partidas de un usuario."""

    @staticmethod
    def combates_de_usuario(user_id: int, community_id: int) -> list[Combat]:
        """Combates donde participo, del más reciente al más antiguo.

        Los participantes y sus usuarios se precargan para no disparar N+1
        al montar el DTO.
        """
        consulta = (
            db.select(Combat)
            .join(CombatParticipant, CombatParticipant.combat_id == Combat.id)
            .where(
                CombatParticipant.user_id == user_id,
                Combat.community_id == community_id,
            )
            .options(
                selectinload(Combat.participants).selectinload(
                    CombatParticipant.user
                )
            )
            .order_by(Combat.played_at.desc(), Combat.id.desc())
        )
        return list(db.session.execute(consulta).scalars().all())

    @staticmethod
    def snapshots_de_usuario(user_id: int, combat_ids: list[int]) -> dict[int, RatingHistory]:
        """Mapa combate → snapshot de mi índice en ese combate (si está procesado)."""
        if not combat_ids:
            return {}
        filas = db.session.execute(
            db.select(RatingHistory).where(
                RatingHistory.user_id == user_id,
                RatingHistory.combat_id.in_(combat_ids),
            )
        ).scalars().all()
        return {fila.combat_id: fila for fila in filas}
