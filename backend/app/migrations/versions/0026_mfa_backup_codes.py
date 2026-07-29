"""Add mfa_backup_codes to users (MFA recovery backup codes)

Revision ID: 0026_mfa_backup_codes
Revises: 0025_notifications
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0026_mfa_backup_codes"
down_revision: Union[str, None] = "0025_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_backup_codes", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "mfa_backup_codes")
