"""Add superseded_by_id to archived_documents (e-Bunsho correction history)

Revision ID: 0022_document_supersede
Revises: 0021_office_tasks
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022_document_supersede"
down_revision: Union[str, None] = "0021_office_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "archived_documents",
        sa.Column(
            "superseded_by_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("archived_documents.archived_document_id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_archived_documents_superseded", "archived_documents", ["superseded_by_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_archived_documents_superseded", table_name="archived_documents")
    op.drop_column("archived_documents", "superseded_by_id")
