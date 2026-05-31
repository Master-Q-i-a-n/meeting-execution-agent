"""add audio segments

Revision ID: 202605310001
Revises: 202605230001
Create Date: 2026-05-31 21:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202605310001"
down_revision: str | None = "202605230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audio_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=True),
        sa.Column("end_time", sa.Float(), nullable=True),
        sa.Column("speaker", sa.String(length=100), nullable=True),
        sa.Column("emotion", sa.String(length=64), nullable=True),
        sa.Column("pause_before_ms", sa.Integer(), nullable=True),
        sa.Column("speech_rate", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_filename", sa.String(length=300), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audio_segments_meeting_id", "audio_segments", ["meeting_id"])


def downgrade() -> None:
    op.drop_index("ix_audio_segments_meeting_id", table_name="audio_segments")
    op.drop_table("audio_segments")
