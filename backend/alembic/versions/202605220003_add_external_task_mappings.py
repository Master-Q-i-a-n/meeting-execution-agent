"""add external task mappings

Revision ID: 202605220003
Revises: 202605220002
Create Date: 2026-05-22 17:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202605220003"
down_revision: str | None = "202605220002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_task_mappings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("action_item_id", sa.String(length=36), nullable=False),
        sa.Column("tool_call_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_task_id", sa.String(length=128), nullable=False),
        sa.Column("external_identifier", sa.String(length=128), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["action_item_id"], ["action_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_call_id"], ["tool_calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "action_item_id", name="uq_external_task_provider_item"),
    )
    op.create_index("ix_external_task_mappings_action_item_id", "external_task_mappings", ["action_item_id"])
    op.create_index("ix_external_task_mappings_provider", "external_task_mappings", ["provider"])
    op.create_index("ix_external_task_mappings_status", "external_task_mappings", ["status"])
    op.create_index("ix_external_task_mappings_tool_call_id", "external_task_mappings", ["tool_call_id"])


def downgrade() -> None:
    op.drop_index("ix_external_task_mappings_tool_call_id", table_name="external_task_mappings")
    op.drop_index("ix_external_task_mappings_status", table_name="external_task_mappings")
    op.drop_index("ix_external_task_mappings_provider", table_name="external_task_mappings")
    op.drop_index("ix_external_task_mappings_action_item_id", table_name="external_task_mappings")
    op.drop_table("external_task_mappings")
