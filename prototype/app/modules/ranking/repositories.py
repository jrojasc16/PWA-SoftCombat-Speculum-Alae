"""Lectura/escritura de Rating y RatingHistory.

Única capa del módulo ranking que toca SQLAlchemy (regla transversal 4): los
servicios trabajan contra esta interfaz y no conocen la sesión ni la BD.
"""

from sqlalchemy.orm import selectinload

from app.extensions import db
from app.modules.ranking.models import Rating, RatingHistory


class RatingRepository:
    """Acceso a datos del índice vivo de los jugadores."""

    @staticmethod
    def get(user_id: int, community_id: int) -> Rating | None:
        """Devuelve el índice de un jugador en una comunidad o None."""
        return db.session.execute(
            db.select(Rating).filter_by(user_id=user_id, community_id=community_id)
        ).scalars().first()

    @staticmethod
    def listar(community_id: int) -> list[Rating]:
        """Índices de la comunidad ordenados por puntos desc (empates por id)."""
        return list(
            db.session.execute(
                db.select(Rating)
                .where(Rating.community_id == community_id)
                .options(selectinload(Rating.user))
                .order_by(Rating.points.desc(), Rating.id.asc())
            )
            .scalars()
            .all()
        )

    @staticmethod
    def add(rating: Rating) -> Rating:
        """Adjunta el índice a la sesión (los existentes ya están rastreados)."""
        db.session.add(rating)
        db.session.flush()
        return rating

    @staticmethod
    def save() -> None:
        """Confirma la transacción en curso (Unit of Work del servicio llamante)."""
        db.session.commit()

    @staticmethod
    def rollback() -> None:
        """Revierte la transacción en curso ante un fallo a mitad del cálculo."""
        db.session.rollback()

    @staticmethod
    def borrar_de_comunidad(community_id: int) -> None:
        """Elimina todos los índices de la comunidad (base del recálculo manual)."""
        db.session.execute(
            db.delete(Rating).where(Rating.community_id == community_id)
        )


class RatingHistoryRepository:
    """Acceso a los snapshots por combate procesado."""

    @staticmethod
    def add(entry: RatingHistory) -> RatingHistory:
        """Persiste un snapshot (flush para disponer del id)."""
        db.session.add(entry)
        db.session.flush()
        return entry

    @staticmethod
    def entradas_de_comunidad(community_id: int) -> list[RatingHistory]:
        """Historial completo de la comunidad en orden de proceso."""
        return list(
            db.session.execute(
                db.select(RatingHistory)
                .where(RatingHistory.community_id == community_id)
                .order_by(RatingHistory.id.asc())
            )
            .scalars()
            .all()
        )

    @staticmethod
    def borrar_de_comunidad(community_id: int) -> None:
        """Elimina el historial de la comunidad (se reconstruye al recalcular)."""
        db.session.execute(
            db.delete(RatingHistory).where(RatingHistory.community_id == community_id)
        )
