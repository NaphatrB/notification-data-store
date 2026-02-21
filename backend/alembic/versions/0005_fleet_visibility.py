"""fleet visibility — add device_id FK to raw_events, create audit_logs table

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- raw_events: add device_id FK ---
    op.add_column(
        "raw_events",
        sa.Column("device_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_raw_events_device_id",
        "raw_events",
        "devices",
        ["device_id"],
        ["id"],
    )
    op.create_index("ix_raw_events_device_id", "raw_events", ["device_id"])

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_target_id", "audit_logs", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_target_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_raw_events_device_id", table_name="raw_events")
    op.drop_constraint("fk_raw_events_device_id", "raw_events", type_="foreignkey")
    op.drop_column("raw_events", "device_id")
