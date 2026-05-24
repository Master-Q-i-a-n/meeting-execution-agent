"""add analysis drafts

Revision ID: 202605210001
Revises: 202605200001
Create Date: 2026-05-21 20:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202605210001"
down_revision: str | None = "202605200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_draft_item_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("meetings", sa.Column("occurred_at", sa.DateTime(), nullable=True))

    op.create_table(
        "analysis_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("decision_summary", sa.Text(), nullable=True),
        sa.Column("raw_result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_drafts_meeting_id", "analysis_drafts", ["meeting_id"])
    op.create_index("ix_analysis_drafts_status", "analysis_drafts", ["status"])

    op.create_table(
        "decisions",
        *_add_draft_item_columns(),
        sa.Column("analysis_draft_id", sa.String(length=36), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_draft_id"], ["analysis_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decisions_analysis_draft_id", "decisions", ["analysis_draft_id"])
    op.create_index("ix_decisions_status", "decisions", ["status"])

    op.create_table(
        "action_items",
        *_add_draft_item_columns(),
        sa.Column("analysis_draft_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_name", sa.String(length=200), nullable=True),
        sa.Column("deadline_text", sa.String(length=200), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["analysis_draft_id"], ["analysis_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_items_analysis_draft_id", "action_items", ["analysis_draft_id"])
    op.create_index("ix_action_items_status", "action_items", ["status"])

    op.create_table(
        "risk_items",
        *_add_draft_item_columns(),
        sa.Column("analysis_draft_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["analysis_draft_id"], ["analysis_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_items_analysis_draft_id", "risk_items", ["analysis_draft_id"])
    op.create_index("ix_risk_items_status", "risk_items", ["status"])

    op.create_table(
        "unconfirmed_items",
        *_add_draft_item_columns(),
        sa.Column("analysis_draft_id", sa.String(length=36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["analysis_draft_id"], ["analysis_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_unconfirmed_items_analysis_draft_id", "unconfirmed_items", ["analysis_draft_id"])
    op.create_index("ix_unconfirmed_items_status", "unconfirmed_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_unconfirmed_items_status", table_name="unconfirmed_items")
    op.drop_index("ix_unconfirmed_items_analysis_draft_id", table_name="unconfirmed_items")
    op.drop_table("unconfirmed_items")

    op.drop_index("ix_risk_items_status", table_name="risk_items")
    op.drop_index("ix_risk_items_analysis_draft_id", table_name="risk_items")
    op.drop_table("risk_items")

    op.drop_index("ix_action_items_status", table_name="action_items")
    op.drop_index("ix_action_items_analysis_draft_id", table_name="action_items")
    op.drop_table("action_items")

    op.drop_index("ix_decisions_status", table_name="decisions")
    op.drop_index("ix_decisions_analysis_draft_id", table_name="decisions")
    op.drop_table("decisions")

    op.drop_index("ix_analysis_drafts_status", table_name="analysis_drafts")
    op.drop_index("ix_analysis_drafts_meeting_id", table_name="analysis_drafts")
    op.drop_table("analysis_drafts")
    op.drop_column("meetings", "occurred_at")
