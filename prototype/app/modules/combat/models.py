"""Modelos ORM: Combat (aggregate, flag processed), CombatParticipant, Confirmation, AuditLog.

El aggregate ``Combat`` es la unidad de persistencia que confirma un duelo y
dispara el recálculo Elo (Sprint 6). ``Confirmation`` (Sprint 5.1) se declara
en este módulo; ``AuditLog`` llega en la tarea 5.3.

Decisiones de diseño:
- ``community_id`` NOT NULL en todas las tablas de negocio (RNF006).
- ``processed`` (default ``False``) es la clave de **idempotencia** del recálculo
  Elo: un combate jamás se reprocesa (regla transversal 2).
- ``client_request_id`` + restricción única por emisor dan **idempotencia del
  reporte**: los reenvíos en modo offline (RF5) no duplican el combate.
"""

from datetime import datetime, timezone

from app.extensions import db
from app.modules.combat.domain.estados import EstadoCombate, ResultadoParticipante

# Marca de tiempo en UTC **sin tz** (SQLite no guarda husos; comparaciones simples).
def _utc_ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Combat(db.Model):
    """Combate individual reportado por la comunidad (aggregate raíz)."""

    __tablename__ = "combats"

    id = db.Column(db.Integer, primary_key=True)
    # RNF006: aislamiento multi-comunidad desde el inicio.
    community_id = db.Column(db.Integer, nullable=False, index=True)
    # Quien envía el reporte (participante o árbitro): autoría del registro.
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # Árbitro asignado: nullable (los reportes entre jugadores no lo traen).
    referee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(
        db.Enum(EstadoCombate), nullable=False, default=EstadoCombate.PENDIENTE
    )
    # Fecha en que se jugó el combate (no puede ser futura).
    played_at = db.Column(db.DateTime, nullable=False)
    # Clave de idempotencia del reporte (offline/reintento); única por emisor.
    client_request_id = db.Column(db.String(64), nullable=True)
    # Idempotencia del recálculo Elo: True = ya fue procesado (nunca se repite).
    processed = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_ahora)

    participants = db.relationship(
        "CombatParticipant",
        back_populates="combat",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CombatParticipant.id",
    )

    confirmations = db.relationship(
        "Confirmation",
        back_populates="combat",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Confirmation.id",
    )

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    referee = db.relationship("User", foreign_keys=[referee_id])

    __table_args__ = (
        # Consulta frecuente: combates de una comunidad por estado (Sprint 4.4/10.3).
        db.Index("ix_combats_community_status", "community_id", "status"),
        # Idempotencia del reporte: la misma clave no puede repetirse por emisor.
        db.UniqueConstraint(
            "community_id",
            "reporter_id",
            "client_request_id",
            name="uq_combats_idempotencia",
        ),
    )

    @property
    def ganador_id(self) -> int | None:
        """id del participante marcado con VICTORIA (None si no hay resultado)."""
        for participante in self.participants:
            if participante.result == ResultadoParticipante.VICTORIA:
                return participante.user_id
        return None

    @property
    def participante_ids(self) -> list[int]:
        """ids de los participantes en orden de declaración."""
        return [p.user_id for p in self.participants]

    def __repr__(self) -> str:  # pragma: no cover - representación de depuración
        return f"<Combat {self.id} {self.status}>"


class CombatParticipant(db.Model):
    """Participante de un combate con el resultado declarado a su favor."""

    __tablename__ = "combat_participants"

    id = db.Column(db.Integer, primary_key=True)
    combat_id = db.Column(
        db.Integer, db.ForeignKey("combats.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    result = db.Column(db.Enum(ResultadoParticipante), nullable=False)
    # RNF006: aislamiento multi-comunidad desde el inicio.
    community_id = db.Column(db.Integer, nullable=False, index=True)

    combat = db.relationship("Combat", back_populates="participants")
    user = db.relationship("User")

    __table_args__ = (
        # Un usuario no puede figurar dos veces en el mismo combate.
        db.UniqueConstraint("combat_id", "user_id", name="uq_combat_user"),
    )

    def __repr__(self) -> str:  # pragma: no cover - representación de depuración
        return f"<CombatParticipant c={self.combat_id} u={self.user_id} {self.result}>"


class Confirmation(db.Model):
    """Confirmación individual de un combate por parte de un usuario.

    Cada participante (o el árbitro asignado) declara una vez qué participante
    ganó. Dos declaraciones coincidentes cierran el combate en ``CONFIRMADO`` y
    discrepantes lo mandan a ``CONFLICTO`` (RF8: dos participantes **o** un
    árbitro; en conflicto prevalece el árbitro).
    """

    __tablename__ = "confirmations"

    id = db.Column(db.Integer, primary_key=True)
    combat_id = db.Column(
        db.Integer, db.ForeignKey("combats.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    # Resultado reportado por el confirmador: {"winner_id": <id del ganador>}.
    # Se guarda como JSON (tipo declarado en el diagrama de clases) para que dos
    # confirmaciones sean comparables directamente: coinciden si ganador_id es igual.
    reported_result = db.Column(db.JSON, nullable=False)
    # RNF006: aislamiento multi-comunidad desde el inicio.
    community_id = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_ahora)

    combat = db.relationship("Combat", back_populates="confirmations")
    user = db.relationship("User")

    __table_args__ = (
        # Un usuario confirma un combate como máximo una vez.
        db.UniqueConstraint("combat_id", "user_id", name="uq_confirmation_user"),
    )

    @property
    def ganador_id(self) -> int | None:
        """id del participante que este confirmador declara ganador."""
        return (self.reported_result or {}).get("winner_id")

    def __repr__(self) -> str:  # pragma: no cover - representación de depuración
        return f"<Confirmation c={self.combat_id} u={self.user_id} winner={self.ganador_id}>"
