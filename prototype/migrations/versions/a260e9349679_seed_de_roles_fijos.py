"""seed de roles fijos

Revision ID: a260e9349679
Revises: a2b46fb341aa
Create Date: 2026-10-05 14:57:03.844207

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a260e9349679'
down_revision = 'a2b46fb341aa'
branch_labels = None
depends_on = None


def upgrade():
    # Seed de los 4 roles fijos del MVP (PROPUESTA §4.3). Migración de DATOS:
    # los roles no se crean en código de aplicación.
    roles = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("permissions", sa.Text),
    )
    op.bulk_insert(
        roles,
        [
            {"id": 1, "name": "jugador", "permissions": None},
            {"id": 2, "name": "arbitro", "permissions": None},
            {"id": 3, "name": "admin", "permissions": None},
            {"id": 4, "name": "super_admin", "permissions": None},
        ],
    )


def downgrade():
    op.execute(
        sa.text("DELETE FROM roles WHERE name IN ('jugador','arbitro','admin','super_admin')")
    )
