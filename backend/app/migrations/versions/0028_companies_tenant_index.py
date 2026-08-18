"""Index companies(tenant_id, is_deleted) for tenant scoping

テナント越境防止のため、ID指定の参照は
`company_id IN (SELECT company_id FROM companies WHERE tenant_id = ? AND is_deleted = false)`
で絞るようになった。この副問い合わせは**全てのID指定リクエストで実行される**が、
companies にはインデックスが1つも無く、毎回シーケンシャルスキャンになる。

会社数はテナント数に比例して増えるため、放置すると利用者が増えるほど
全エンドポイントが一様に遅くなる。

Revision ID: 0028_companies_tenant_index
Revises: 0027_audit_log_tenant_nullable
Create Date: 2026-08-18

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0028_companies_tenant_index"
down_revision: str | None = "0027_audit_log_tenant_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_companies_tenant", "companies", ["tenant_id", "is_deleted"])


def downgrade() -> None:
    op.drop_index("ix_companies_tenant", table_name="companies")
