"""create raw_events table

Revision ID: 0001
Revises:
Create Date: 2026-02-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("message_hash", sa.Text(), nullable=True),
        sa.Column("package_name", sa.Text(), nullable=False),
        sa.Column("app_name", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("big_text", sa.Text(), nullable=True),
        sa.Column(
            "event_timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column(
            "received_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # Indexes
    op.create_unique_constraint(
        "uq_raw_events_message_hash", "raw_events", ["message_hash"]
    )
    op.create_index(
        "ix_raw_events_event_timestamp", "raw_events", ["event_timestamp"]
    )
    op.create_index(
        "ix_raw_events_source_type", "raw_events", ["source_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_raw_events_source_type", table_name="raw_events")
    op.drop_index("ix_raw_events_event_timestamp", table_name="raw_events")
    op.drop_constraint(
        "uq_raw_events_message_hash", "raw_events", type_="unique"
    )
    op.drop_table("raw_events")
