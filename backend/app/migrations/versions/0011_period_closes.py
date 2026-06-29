"""Add period_closes table for monthly closing

Revision ID: 0011_period_closes
Revises: 0010_indexes
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_period_closes"
down_revision: Union[str, None] = "0010_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "period_closes",
        sa.Column("close_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("closed_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_period_closes_company", "period_closes", ["company_id"])
    op.create_index("ix_period_closes_period", "period_closes", ["company_id", "year", "month"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_period_closes_period", table_name="period_closes")
    op.drop_index("ix_period_closes_company", table_name="period_closes")
    op.drop_table("period_closes")
