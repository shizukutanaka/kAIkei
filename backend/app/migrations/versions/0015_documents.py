"""Add archived_documents table

Revision ID: 0015_documents
Revises: 0014_bank_reconciliation
Create Date: 2026-06-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_documents"
down_revision: str | None = "0014_bank_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "archived_documents",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_extension", sa.String(10), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("transaction_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("counterparty_name", sa.String(255), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("timestamp_token", sa.Text(), nullable=True),
        sa.Column("timestamp_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "journal_header_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_headers.journal_header_id"),
            nullable=True,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index(
        "idx_doc_search_requirements",
        "archived_documents",
        ["company_id", "transaction_date", "transaction_amount", "counterparty_name"],
    )
    op.create_index("ix_archived_documents_company_file_hash", "archived_documents", ["company_id", "file_hash"])


def downgrade() -> None:
    op.drop_index("ix_archived_documents_company_file_hash", table_name="archived_documents")
    op.drop_index("idx_doc_search_requirements", table_name="archived_documents")
    op.drop_table("archived_documents")
