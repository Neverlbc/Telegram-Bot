"""create analytics events table

Revision ID: 20260427_0001
Revises:
Create Date: 2026-04-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260427_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("analytics_events"):
        op.create_table(
            "analytics_events",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("telegram_id", sa.BigInteger(), nullable=True),
            sa.Column("chat_id", sa.BigInteger(), nullable=True),
            sa.Column("chat_type", sa.String(length=32), nullable=True),
            sa.Column("message_id", sa.BigInteger(), nullable=True),
            sa.Column("event_type", sa.String(length=32), nullable=False),
            sa.Column("event_name", sa.String(length=96), nullable=False),
            sa.Column("module", sa.String(length=64), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=True),
            sa.Column("language", sa.String(length=8), nullable=True),
            sa.Column("state", sa.String(length=128), nullable=True),
            sa.Column("event_data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_events")),
        )

    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("analytics_events")}

    def create_index(name: str, columns: list[str]) -> None:
        if name not in existing_indexes:
            op.create_index(name, "analytics_events", columns, unique=False)

    create_index(op.f("ix_analytics_events_telegram_id"), ["telegram_id"])
    create_index(op.f("ix_analytics_events_chat_id"), ["chat_id"])
    create_index(op.f("ix_analytics_events_event_type"), ["event_type"])
    create_index(op.f("ix_analytics_events_event_name"), ["event_name"])
    create_index(op.f("ix_analytics_events_module"), ["module"])
    create_index(op.f("ix_analytics_events_action"), ["action"])
    create_index(op.f("ix_analytics_events_language"), ["language"])
    create_index("idx_analytics_created_at", ["created_at"])
    create_index("idx_analytics_user_created", ["telegram_id", "created_at"])
    create_index("idx_analytics_module_action_created", ["module", "action", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("analytics_events"):
        return
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("analytics_events")}

    def drop_index(name: str) -> None:
        if name in existing_indexes:
            op.drop_index(name, table_name="analytics_events")

    drop_index("idx_analytics_module_action_created")
    drop_index("idx_analytics_user_created")
    drop_index("idx_analytics_created_at")
    drop_index(op.f("ix_analytics_events_language"))
    drop_index(op.f("ix_analytics_events_action"))
    drop_index(op.f("ix_analytics_events_module"))
    drop_index(op.f("ix_analytics_events_event_name"))
    drop_index(op.f("ix_analytics_events_event_type"))
    drop_index(op.f("ix_analytics_events_chat_id"))
    drop_index(op.f("ix_analytics_events_telegram_id"))
    op.drop_table("analytics_events")
