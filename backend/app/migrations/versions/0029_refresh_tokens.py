"""Add refresh_tokens ledger (rotation + reuse detection)

リフレッシュトークンはブラウザの localStorage に置かれるため XSS で盗まれ得るが、
サーバ側に発行記録が無かったため、盗まれたトークンは有効期限まで使い放題で、
更新のたびに期限が延びるため実質無期限だった。利用者を無効化・削除しても
更新は通り続けていた。

1回のログインを family とし、更新のたびに同じ family へ行を積む。使用済みの
トークンが再提示されたら盗難の疑いとして family ごと失効させる
（RFC 9700 §4.14.2 の refresh token rotation + reuse detection）。

Revision ID: 0029_refresh_tokens
Revises: 0028_companies_tenant_index
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_refresh_tokens"
down_revision: str | None = "0028_companies_tenant_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("token_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # family 単位の一括失効と、利用者単位の全セッション失効で引く。
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
