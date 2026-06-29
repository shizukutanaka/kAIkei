"""Add attendance_records table

Revision ID: 0006_attendance
Revises: 0005_year_end
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_attendance"
down_revision: Union[str, None] = "0005_year_end"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_records",
        sa.Column("attendance_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.employee_id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("clock_in", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clock_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("break_minutes", sa.Integer, server_default="60", nullable=False),
        sa.Column("work_minutes", sa.Integer, server_default="0", nullable=False),
        sa.Column("overtime_minutes", sa.Integer, server_default="0", nullable=False),
        sa.Column("leave_type", sa.String(20), server_default="none", nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_attendance_employee_date", "attendance_records", ["employee_id", "work_date"])


def downgrade() -> None:
    op.drop_index("ix_attendance_employee_date", table_name="attendance_records")
    op.drop_table("attendance_records")
