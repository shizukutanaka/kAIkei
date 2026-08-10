"""Add webhook_endpoints and webhook_deliveries tables

Revision ID: 0013_webhooks
Revises: 0012_audit_logs
Create Date: 2026-07-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0013_webhooks"
down_revision: str | None = "0017_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("webhook_endpoint_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("secret", sa.String(200), nullable=False),
        sa.Column("subscribed_events", JSONB, nullable=False, server_default="[]"),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_webhook_endpoints_tenant", "webhook_endpoints", ["tenant_id"])
    op.create_index("ix_webhook_endpoints_active", "webhook_endpoints", ["tenant_id", "is_active"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("webhook_delivery_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "webhook_endpoint_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.webhook_endpoint_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("last_status_code", sa.Integer, nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_webhook_deliveries_endpoint", "webhook_deliveries", ["webhook_endpoint_id"])
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status", "next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_status", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_endpoint", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_webhook_endpoints_active", table_name="webhook_endpoints")
    op.drop_index("ix_webhook_endpoints_tenant", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
