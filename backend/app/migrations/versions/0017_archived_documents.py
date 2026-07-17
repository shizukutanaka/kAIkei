"""Add archived_documents table for e-Bunsho (電帳法) storage

Revision ID: 0017_archived_documents
Revises: 0016_tax_adjustment_rules
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_archived_documents"
down_revision: Union[str, None] = "0016_tax_adjustment_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "archived_documents",
        sa.Column("archived_document_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("company_id", sa.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric(15, 4), nullable=True),
        sa.Column("counterparty_name", sa.String(200), nullable=True),
        sa.Column(
            "linked_journal_header_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("journal_headers.journal_header_id"),
            nullable=True,
        ),
        sa.Column("registered_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # 電帳法の検索3軸に対応するインデックス。
    op.create_index("ix_archived_documents_company", "archived_documents", ["company_id"])
    op.create_index("ix_archived_documents_date", "archived_documents", ["company_id", "transaction_date"])
    op.create_index("ix_archived_documents_amount", "archived_documents", ["company_id", "amount"])
    op.create_index("ix_archived_documents_hash", "archived_documents", ["file_hash"])


def downgrade() -> None:
    op.drop_index("ix_archived_documents_hash", table_name="archived_documents")
    op.drop_index("ix_archived_documents_amount", table_name="archived_documents")
    op.drop_index("ix_archived_documents_date", table_name="archived_documents")
    op.drop_index("ix_archived_documents_company", table_name="archived_documents")
    op.drop_table("archived_documents")
