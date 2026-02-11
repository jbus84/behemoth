"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-10
"""

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("strategy_id", sa.String(), nullable=False),
        sa.Column("pair", sa.String(), nullable=False),
        sa.Column("entry_ts", sa.DateTime(timezone=True)),
        sa.Column("exit_ts", sa.DateTime(timezone=True)),
        sa.Column("side", sa.Enum("LONG", "SHORT", name="side"), nullable=False),
        sa.Column("active_leg", sa.Enum("X", "Y", name="activeleg"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "OPEN", "CLOSING", "CLOSED", "CANCELLED", "FAILED", name="positionstatus"
            ),
            nullable=False,
        ),
        sa.Column("entry_price", sa.Float()),
        sa.Column("exit_price", sa.Float()),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("pnl_bps", sa.Float()),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_positions_pair_status", "positions", ["pair", "status"])
    op.create_index("ix_positions_exit_ts", "positions", ["exit_ts"])

    op.create_table(
        "orders",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("position_id", sa.String(), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("NEW", "SUBMITTED", "FILLED", "CANCELLED", "FAILED", name="orderstatus"),
            nullable=False,
        ),
        sa.Column(
            "order_type", sa.Enum("MARKET", "LIMIT", "STOP", name="ordertype"), nullable=False
        ),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("price", sa.Float()),
        sa.Column("slippage_bps", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_orders_position_id", "orders", ["position_id"])

    op.create_table(
        "position_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("position_id", sa.String(), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_position_events_position_id", "position_events", ["position_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("position_id", sa.String(), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_index("ix_position_events_position_id", table_name="position_events")
    op.drop_index("ix_orders_position_id", table_name="orders")
    op.drop_index("ix_positions_exit_ts", table_name="positions")
    op.drop_index("ix_positions_pair_status", table_name="positions")
    op.drop_table("idempotency_keys")
    op.drop_table("position_events")
    op.drop_table("orders")
    op.drop_table("positions")
    op.execute("DROP TYPE IF EXISTS ordertype")
    op.execute("DROP TYPE IF EXISTS orderstatus")
    op.execute("DROP TYPE IF EXISTS positionstatus")
    op.execute("DROP TYPE IF EXISTS activeleg")
    op.execute("DROP TYPE IF EXISTS side")
