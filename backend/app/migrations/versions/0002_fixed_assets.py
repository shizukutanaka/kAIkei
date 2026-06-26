"""Add fixed_assets and depreciation_records tables

Revision ID: 0002_fixed_assets
Revises: 0001_initial
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_fixed_assets"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fixed_assets",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("asset_code", sa.String(50), nullable=False),
        sa.Column("asset_name", sa.String(200), nullable=False),
        sa.Column("asset_category", sa.String(50), nullable=False),
        sa.Column("acquisition_date", sa.Date, nullable=False),
        sa.Column("acquisition_cost", sa.Numeric(15, 4), nullable=False),
        sa.Column("useful_life_months", sa.Integer, nullable=False),
        sa.Column("depreciation_method", sa.String(20), server_default="straight_line", nullable=False),
        sa.Column("salvage_value", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("accumulated_depreciation", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id"), nullable=True),
        sa.Column("is_disposed", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("disposal_date", sa.Date, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "depreciation_records",
        sa.Column("record_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.asset_id"), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("depreciation_amount", sa.Numeric(15, 4), nullable=False),
        sa.Column("accumulated_amount", sa.Numeric(15, 4), nullable=False),
        sa.Column("journal_header_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journal_headers.journal_header_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("depreciation_records")
    op.drop_table("fixed_assets")
