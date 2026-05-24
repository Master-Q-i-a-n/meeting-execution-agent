"""add reminders

Revision ID: 202605230001
Revises: 202605220003
Create Date: 2026-05-23 10:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202605230001"
down_revision: str | None = "202605220003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("action_item_id", sa.String(length=36), nullable=False),
        sa.Column("reminder_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("unique_key", sa.String(length=160), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["action_item_id"], ["action_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unique_key", name="uq_reminders_unique_key"),
    )
    op.create_index("ix_reminders_action_item_id", "reminders", ["action_item_id"])
    op.create_index("ix_reminders_due_at", "reminders", ["due_at"])
    op.create_index("ix_reminders_reminder_type", "reminders", ["reminder_type"])
    op.create_index("ix_reminders_status", "reminders", ["status"])


def downgrade() -> None:
    op.drop_index("ix_reminders_status", table_name="reminders")
    op.drop_index("ix_reminders_reminder_type", table_name="reminders")
    op.drop_index("ix_reminders_due_at", table_name="reminders")
    op.drop_index("ix_reminders_action_item_id", table_name="reminders")
    op.drop_table("reminders")
