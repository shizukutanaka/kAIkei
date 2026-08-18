"""Add employees.dependents (扶養親族等の数)

月次の源泉所得税は、本来「給与所得の源泉徴収税額表」を社会保険料等控除後の
給与と**扶養親族等の数**で引く。この数を保持していなかったため、総支給の5%を
掛ける概算になっており、実測でおよそ2倍を天引きしていた。

扶養控除は年末調整でも使う（従来はリクエストごとに dependents_override で
渡していた）ため、従業員に持たせる。

Revision ID: 0031_employee_dependents
Revises: 0030_payroll_statutory_fields
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_employee_dependents"
down_revision: str | None = "0030_payroll_statutory_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("dependents", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("employees", "dependents")
