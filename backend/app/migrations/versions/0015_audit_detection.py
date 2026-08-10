"""Add audit_detection_logs table for risk detection

Revision ID: 0015_audit_detection
Revises: 0014_bank_statements
Create Date: 2026-07-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0015_audit_detection"
down_revision: str | None = "0014_bank_statements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_detection_logs",
        sa.Column("audit_detection_log_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column(
            "journal_header_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("journal_headers.journal_header_id"),
            nullable=True,
        ),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("reviewed_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_detection_company", "audit_detection_logs", ["company_id"])
    op.create_index("ix_audit_detection_status", "audit_detection_logs", ["company_id", "status"])
    op.create_index("ix_audit_detection_journal", "audit_detection_logs", ["journal_header_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_detection_journal", table_name="audit_detection_logs")
    op.drop_index("ix_audit_detection_status", table_name="audit_detection_logs")
    op.drop_index("ix_audit_detection_company", table_name="audit_detection_logs")
    op.drop_table("audit_detection_logs")
