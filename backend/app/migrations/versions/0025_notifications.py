"""Add notifications and notification_preferences tables

These models existed since the base schema but never had an Alembic migration,
so `alembic upgrade head` did not create them in real deployments (only the test
harness' Base.metadata.create_all did). This migration closes that gap so the
notification feature works in production.

Revision ID: 0025_notifications
Revises: 0024_mfa_replay_guard
Create Date: 2026-07-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_notifications"
down_revision: str | None = "0024_mfa_replay_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("action_url", sa.String(500), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "is_read"])
    op.create_index("ix_notifications_tenant", "notifications", ["tenant_id", "created_at"])

    op.create_table(
        "notification_preferences",
        sa.Column("preference_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("channel_inapp", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("channel_email", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("channel_push", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("channel_webhook", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # 1ユーザー×1カテゴリにつき設定は1行（サービス層のupsert前提）。
    op.create_index(
        "ux_notification_preferences_user_category",
        "notification_preferences",
        ["user_id", "category"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_notification_preferences_user_category", table_name="notification_preferences")
    op.drop_table("notification_preferences")
    op.drop_index("ix_notifications_tenant", table_name="notifications")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_table("notifications")
