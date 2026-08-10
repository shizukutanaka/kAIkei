"""Add MFA (TOTP) columns to users

Revision ID: 0023_user_mfa
Revises: 0022_document_supersede
Create Date: 2026-07-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_user_mfa"
down_revision: str | None = "0022_document_supersede"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")
