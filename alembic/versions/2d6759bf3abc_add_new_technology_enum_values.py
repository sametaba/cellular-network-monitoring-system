"""add_new_technology_enum_values

Adds 5G, WCDMA, GSM, Unknown to the technology PostgreSQL enum type.

PostgreSQL does NOT allow ALTER TYPE ... ADD VALUE inside a transaction block
when the type already exists and has data.  We run these statements in
AUTOCOMMIT mode to satisfy this constraint.

Revision ID: 2d6759bf3abc
Revises: 75073036bb82
Create Date: 2026-04-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2d6759bf3abc"
down_revision: Union[str, None] = "75073036bb82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_VALUES = ("5G", "WCDMA", "GSM", "Unknown")


def upgrade() -> None:
    # Alembic'in açtığı transaction'ı kapat; ALTER TYPE ... ADD VALUE
    # transaction bloğu dışında çalışması gerekiyor.
    op.execute(sa.text("COMMIT"))
    for val in _NEW_VALUES:
        op.execute(
            sa.text(f"ALTER TYPE technology ADD VALUE IF NOT EXISTS '{val}'")
        )


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum type without
    # recreating it (which would require rewriting the table).  This migration
    # is intentionally not reversible via Alembic.
    pass
