"""Add mfa_last_used_step to users (TOTP anti-replay tracking)

Revision ID: 0024_mfa_replay_guard
Revises: 0023_user_mfa
Create Date: 2026-07-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_mfa_replay_guard"
down_revision: str | None = "0023_user_mfa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_last_used_step", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "mfa_last_used_step")
