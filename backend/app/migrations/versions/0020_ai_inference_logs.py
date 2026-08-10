"""Add ai_inference_logs table for AI inference audit trail

Revision ID: 0020_ai_inference_logs
Revises: 0019_tenant_security_policies
Create Date: 2026-07-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0020_ai_inference_logs"
down_revision: str | None = "0019_tenant_security_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_inference_logs",
        sa.Column("ai_inference_log_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("input_summary", sa.Text, nullable=True),
        sa.Column("suggestion", JSONB, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("provider", sa.String(30), nullable=True),
        sa.Column("applied", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("correction_diff", JSONB, nullable=True),
        sa.Column(
            "journal_header_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("journal_headers.journal_header_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_inference_logs_company", "ai_inference_logs", ["company_id"])
    op.create_index("ix_ai_inference_logs_source", "ai_inference_logs", ["company_id", "source_type"])


def downgrade() -> None:
    op.drop_index("ix_ai_inference_logs_source", table_name="ai_inference_logs")
    op.drop_index("ix_ai_inference_logs_company", table_name="ai_inference_logs")
    op.drop_table("ai_inference_logs")
