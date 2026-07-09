"""Add approval_policies table for amount/document-based approval routing

Revision ID: 0018_approval_policies
Revises: 0017_archived_documents
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_approval_policies"
down_revision: Union[str, None] = "0017_archived_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approval_policies",
        sa.Column("approval_policy_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("min_amount", sa.Numeric(15, 4), nullable=True),
        sa.Column("max_amount", sa.Numeric(15, 4), nullable=True),
        sa.Column("approver_role", sa.String(50), nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_approval_policies_lookup", "approval_policies", ["company_id", "document_type", "is_active"]
    )


def downgrade() -> None:
    op.drop_index("ix_approval_policies_lookup", table_name="approval_policies")
    op.drop_table("approval_policies")
