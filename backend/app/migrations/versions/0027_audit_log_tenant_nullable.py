"""Allow audit_logs.tenant_id to be NULL (pre-authentication events)

監査ログのミドルウェアは tenant_id に固定のゼロUUIDを入れていたため、
tenants への外部キー制約に必ず違反し、全ての監査ログ書き込みが失敗していた
（例外は握り潰され警告ログだけが出る）。ミドルウェア側はJWTの利用者から
実際の tenant_id を引くよう修正するが、ログイン失敗のような**認証前**の
イベントには紐づくテナントが無い。

こうしたイベントこそ監査上の価値が高いので、捨てずに残せるよう NULL を許可する。

Revision ID: 0027_audit_log_tenant_nullable
Revises: 0026_mfa_backup_codes
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_audit_log_tenant_nullable"
down_revision: str | None = "0026_mfa_backup_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "audit_logs",
        "tenant_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # NULL のまま戻すと NOT NULL 制約を張れないため、先に該当行を削除する。
    op.execute(sa.text("DELETE FROM audit_logs WHERE tenant_id IS NULL"))
    op.alter_column(
        "audit_logs",
        "tenant_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
