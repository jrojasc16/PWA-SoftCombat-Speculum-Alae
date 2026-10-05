"""Modelos del módulo IAM: Role y User.

Decisiones de diseño (PROPUESTA_NUEVO_STACK.md §4.3 y trazabilidad §7):
- Los roles viven en la tabla ``roles`` (no enum en código) para dejar listo el
  camino a roles dinámicos (RF3/RF4 pospuestos). El campo ``permissions`` se
  conserva como JSON de texto para ese futuro; en el MVP no se evalúa.
- ``User.community_id`` es NOT NULL desde el inicio (RNF006, aislamiento
  multi-comunidad futuro).
"""

from datetime import datetime, timezone

from app.extensions import db


class Role(db.Model):
    """Rol fijo del sistema: jugador, arbitro, admin, super_admin (seed en migración)."""

    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    # Reservado para RF3 (permisos por rol). Texto JSON; sin uso en el MVP.
    permissions = db.Column(db.Text, nullable=True)

    users = db.relationship("User", back_populates="role", lazy=True)

    def __repr__(self) -> str:  # pragma: no cover - representación de depuración
        return f"<Role {self.name}>"


class User(db.Model):
    """Usuario registrado de la comunidad."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    # RNF006: aislamiento multi-comunidad desde el inicio.
    community_id = db.Column(db.Integer, nullable=False, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    role = db.relationship("Role", back_populates="users")

    # — Integración con Flask-Login —
    @property
    def is_active(self) -> bool:
        return self.active

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    def __repr__(self) -> str:  # pragma: no cover - representación de depuración
        return f"<User {self.email}>"
