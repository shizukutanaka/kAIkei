"""Add tenant_security_policies table for MFA/IP-allowlist policies

Revision ID: 0019_tenant_security_policies
Revises: 0018_approval_policies
Create Date: 2026-07-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0019_tenant_security_policies"
down_revision: str | None = "0018_approval_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_security_policies",
        sa.Column("tenant_security_policy_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False, unique=True),
        sa.Column("require_mfa", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("allowed_ip_cidrs", JSONB, nullable=False, server_default="[]"),
        sa.Column("session_timeout_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("password_min_length", sa.Integer, nullable=False, server_default="8"),
        sa.Column("max_failed_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tenant_security_policies")
