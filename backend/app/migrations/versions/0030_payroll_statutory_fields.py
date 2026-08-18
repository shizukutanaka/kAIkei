"""Add fields required to compute social insurance statutorily

月次給与の社会保険料が「総額の15%」という概算だったのは、正しく計算するための
情報をモデルが持っていなかったことが原因。等級表も保険料の折半計算も
サービスとしては実装済みで、入力が足りていなかった。

- employees.birth_date: 介護保険（第2号被保険者・40歳以上65歳未満）の判定に必要
- companies.health_insurance_rate / care_insurance_rate: 健康保険・介護保険の
  料率は都道府県と年度で変わる（協会けんぽ）。未設定なら代表値を使う

いずれも NULL 許容。既存データは移行不要で、設定した会社から順に正確になる。

Revision ID: 0030_payroll_statutory_fields
Revises: 0029_refresh_tokens
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_payroll_statutory_fields"
down_revision: str | None = "0029_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("companies", sa.Column("health_insurance_rate", sa.Numeric(6, 5), nullable=True))
    op.add_column("companies", sa.Column("care_insurance_rate", sa.Numeric(6, 5), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "care_insurance_rate")
    op.drop_column("companies", "health_insurance_rate")
    op.drop_column("employees", "birth_date")
