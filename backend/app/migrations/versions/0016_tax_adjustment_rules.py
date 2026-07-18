"""Add tax_adjustment_rules table for corporate-tax adjustments

Revision ID: 0016_tax_adjustment_rules
Revises: 0015_audit_detection
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_tax_adjustment_rules"
down_revision: Union[str, None] = "0015_audit_detection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tax_adjustment_rules",
        sa.Column("tax_adjustment_rule_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("adjustment_type", sa.String(20), nullable=False),
        sa.Column("calculation_method", sa.String(30), nullable=False),
        sa.Column("rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("limit_amount", sa.Numeric(15, 4), nullable=True),
        sa.Column("fixed_amount", sa.Numeric(15, 4), nullable=True),
        sa.Column("target_account_code", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tax_adjustment_rules_company", "tax_adjustment_rules", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_tax_adjustment_rules_company", table_name="tax_adjustment_rules")
    op.drop_table("tax_adjustment_rules")
