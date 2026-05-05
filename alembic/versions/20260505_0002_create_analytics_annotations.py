"""create analytics annotations table

Revision ID: 20260505_0002
Revises: 20260427_0001
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260505_0002"
down_revision = "20260427_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("analytics_annotations"):
        op.create_table(
            "analytics_annotations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("event_date", sa.Date(), nullable=False),
            sa.Column("title", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("color", sa.String(length=20), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_annotations")),
        )

    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("analytics_annotations")}
    if "idx_annotations_event_date" not in existing_indexes:
        op.create_index(
            "idx_annotations_event_date",
            "analytics_annotations",
            ["event_date"],
            unique=False,
        )
    if op.f("ix_analytics_annotations_event_date") not in existing_indexes:
        op.create_index(
            op.f("ix_analytics_annotations_event_date"),
            "analytics_annotations",
            ["event_date"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("analytics_annotations"):
        return
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("analytics_annotations")}
    for name in ("idx_annotations_event_date", op.f("ix_analytics_annotations_event_date")):
        if name in existing_indexes:
            op.drop_index(name, table_name="analytics_annotations")
    op.drop_table("analytics_annotations")
