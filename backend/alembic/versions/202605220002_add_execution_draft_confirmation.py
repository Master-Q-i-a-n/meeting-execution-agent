"""add execution draft confirmation

Revision ID: 202605220002
Revises: 202605220001
Create Date: 2026-05-22 15:40:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202605220002"
down_revision: str | None = "202605220001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("action_items", sa.Column("priority", sa.String(length=32), nullable=True))
    op.create_table(
        "draft_confirmation_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_draft_id", sa.String(length=36), nullable=False),
        sa.Column("agent_suggestion_json", sa.JSON(), nullable=False),
        sa.Column("confirmed_draft_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["analysis_draft_id"], ["analysis_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_draft_confirmation_snapshots_analysis_draft_id",
        "draft_confirmation_snapshots",
        ["analysis_draft_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_draft_confirmation_snapshots_analysis_draft_id",
        table_name="draft_confirmation_snapshots",
    )
    op.drop_table("draft_confirmation_snapshots")
    op.drop_column("action_items", "priority")
