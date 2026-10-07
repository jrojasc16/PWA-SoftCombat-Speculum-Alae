"""Modelos ORM: Rating (elo actual, n.º de combates) y RatingHistory (trazabilidad).

- ``Rating`` es un **snapshot vivo** del índice de un jugador en una comunidad;
  se crea con el valor inicial del reglamento (1500) el primer día y solo lo
  tocan los servicios del módulo (recálculo on-write, Sprint 6.2).
- ``RatingHistory`` guarda un registro **por combate procesado** con el valor
  antes y después: es la traza auditable del recálculo (y la fuente para
  reconstruir la evolución en el historial del Sprint 7).

RNF006: todas las tablas de negocio llevan ``community_id``.
"""

from datetime import datetime, timezone

from app.extensions import db
from app.modules.ranking.domain.constants import RATING_INICIAL


def _utc_ahora() -> datetime:
    """Marca de tiempo en UTC sin tz (SQLite no almacena husos)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Rating(db.Model):
    """Índice Elo actual de un usuario en una comunidad."""

    __tablename__ = "ratings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    community_id = db.Column(db.Integer, nullable=False, index=True)
    points = db.Column(db.Float, nullable=False, default=RATING_INICIAL)
    matches_played = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utc_ahora)

    user = db.relationship("User")

    __table_args__ = (
        # Un índice por usuario y comunidad (aislamiento multi-comunidad).
        db.UniqueConstraint("user_id", "community_id", name="uq_rating_user_community"),
    )

    def __repr__(self) -> str:  # pragma: no cover - representación de depuración
        return f"<Rating u={self.user_id} c={self.community_id} p={self.points:.1f}>"


class RatingHistory(db.Model):
    """Snapshot del índice de un jugador al procesar un combate."""

    __tablename__ = "rating_history"

    id = db.Column(db.Integer, primary_key=True)
    combat_id = db.Column(
        db.Integer, db.ForeignKey("combats.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    community_id = db.Column(db.Integer, nullable=False, index=True)
    points_before = db.Column(db.Float, nullable=False)
    points_after = db.Column(db.Float, nullable=False)
    # Nº de combates del jugador **después** de este combate (alimenta la tabla t).
    matches_played = db.Column(db.Integer, nullable=False)
    # Constante k y percentil usados en el cálculo (trazabilidad del Art. 30).
    k = db.Column(db.Float, nullable=False)
    percentil = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_ahora)

    combat = db.relationship("Combat")
    user = db.relationship("User")

    __table_args__ = (
        # Un registro por jugador y combate (el recálculo los reconstruye).
        db.UniqueConstraint("combat_id", "user_id", name="uq_history_combat_user"),
    )

    def __repr__(self) -> str:  # pragma: no cover - representación de depuración
        return f"<RatingHistory c={self.combat_id} u={self.user_id} {self.points_before}->{self.points_after}>"
