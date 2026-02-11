"""add account_state and position allocation fields

Revision ID: 003_account_state
Revises: 002_create_guardrail_state
Create Date: 2026-02-10
"""

import sqlalchemy as sa
from alembic import op

revision = "003_account_state"
down_revision = "002_create_guardrail_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_state",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("strategy_id", sa.String(), nullable=False),
        sa.Column("equity", sa.Float(), nullable=False),
        sa.Column("peak_equity", sa.Float(), nullable=False),
        sa.Column("day_start_equity", sa.Float(), nullable=False),
        sa.Column("day_start_date", sa.Date(), nullable=False),
        sa.Column("consecutive_losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("halted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("halt_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("strategy_id", name="uq_account_state_strategy"),
    )
    op.create_index("ix_account_state_strategy_id", "account_state", ["strategy_id"])

    op.add_column("positions", sa.Column("notional_usd", sa.Float(), nullable=True))
    op.add_column("positions", sa.Column("alloc_frac", sa.Float(), nullable=True))
    op.add_column("positions", sa.Column("entry_equity", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("positions", "entry_equity")
    op.drop_column("positions", "alloc_frac")
    op.drop_column("positions", "notional_usd")
    op.drop_index("ix_account_state_strategy_id", table_name="account_state")
    op.drop_table("account_state")
