"""add meeting chunks

Revision ID: 202605220001
Revises: 202605210001
Create Date: 2026-05-22 00:01:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202605220001"
down_revision: str | None = "202605210001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_draft_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(length=64), nullable=False),
        sa.Column("index_status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["analysis_draft_id"], ["analysis_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("qdrant_point_id"),
    )
    op.create_index("ix_meeting_chunks_analysis_draft_id", "meeting_chunks", ["analysis_draft_id"])
    op.create_index("ix_meeting_chunks_index_status", "meeting_chunks", ["index_status"])
    op.create_index("ix_meeting_chunks_meeting_id", "meeting_chunks", ["meeting_id"])
    op.create_index("ix_meeting_chunks_source_id", "meeting_chunks", ["source_id"])
    op.create_index("ix_meeting_chunks_source_type", "meeting_chunks", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_meeting_chunks_source_type", table_name="meeting_chunks")
    op.drop_index("ix_meeting_chunks_source_id", table_name="meeting_chunks")
    op.drop_index("ix_meeting_chunks_meeting_id", table_name="meeting_chunks")
    op.drop_index("ix_meeting_chunks_index_status", table_name="meeting_chunks")
    op.drop_index("ix_meeting_chunks_analysis_draft_id", table_name="meeting_chunks")
    op.drop_table("meeting_chunks")
