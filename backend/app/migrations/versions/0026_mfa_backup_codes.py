"""Add mfa_backup_codes to users (MFA recovery backup codes)

Revision ID: 0026_mfa_backup_codes
Revises: 0025_notifications
Create Date: 2026-07-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_mfa_backup_codes"
down_revision: str | None = "0025_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_backup_codes", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "mfa_backup_codes")
