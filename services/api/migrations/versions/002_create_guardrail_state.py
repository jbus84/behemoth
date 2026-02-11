"""create guardrail_state table

Revision ID: 002_create_guardrail_state
Revises: 001_create_positions
Create Date: 2026-02-10
"""

import sqlalchemy as sa
from alembic import op

revision = "002_create_guardrail_state"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "guardrail_state",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("strategy_id", sa.String(), nullable=False),
        sa.Column("pair", sa.String(), nullable=False),
        sa.Column("loss_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pause_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("strategy_id", "pair", name="uq_guardrail_state"),
    )
    op.create_index("ix_guardrail_state_strategy_id", "guardrail_state", ["strategy_id"])
    op.create_index("ix_guardrail_state_pair", "guardrail_state", ["pair"])


def downgrade():
    op.drop_index("ix_guardrail_state_pair", table_name="guardrail_state")
    op.drop_index("ix_guardrail_state_strategy_id", table_name="guardrail_state")
    op.drop_table("guardrail_state")
