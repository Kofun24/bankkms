"""add admin role and none access level

Revision ID: f2fde163c850
Revises: e76f2a9e5551
Create Date: 2026-09-07 10:56:38.856667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2fde163c850'
down_revision: Union[str, Sequence[str], None] = 'e76f2a9e5551'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres requires ALTER TYPE ... ADD VALUE to run outside a
    # transaction block in older versions; Alembic/psycopg2 handles this
    # automatically for simple ADD VALUE statements in modern Postgres (17.x).
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'admin'")
    op.execute("ALTER TYPE sessionrole ADD VALUE IF NOT EXISTS 'admin'")
    op.execute("ALTER TYPE accesslevel ADD VALUE IF NOT EXISTS 'none'")


def downgrade() -> None:
    # Postgres does not support removing a value from an enum type directly.
    # A true downgrade would require recreating the enum type without the
    # value and migrating all dependent columns — out of scope for this
    # project. This is a known, one-way migration.
    raise NotImplementedError(
        "Cannot remove enum values in Postgres without recreating the type. "
        "This migration is one-way."
    )