"""add battery logs table

Revision ID: 0010
Revises: 0009
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_battery_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("battery_percentage", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_device_battery_logs_created_at",
        "device_battery_logs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_device_battery_logs_device_id",
        "device_battery_logs",
        ["device_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_device_battery_logs_device_id", table_name="device_battery_logs")
    op.drop_index("ix_device_battery_logs_created_at", table_name="device_battery_logs")
    op.drop_table("device_battery_logs")
