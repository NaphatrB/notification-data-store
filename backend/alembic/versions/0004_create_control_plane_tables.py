"""create control plane tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- devices ---
    op.create_table(
        "devices",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("device_uuid", sa.Text(), nullable=False),
        sa.Column("device_name", sa.Text(), nullable=True),
        sa.Column("device_model", sa.Text(), nullable=True),
        sa.Column("android_version", sa.Text(), nullable=True),
        sa.Column("app_version", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_devices_device_uuid", "devices", ["device_uuid"]
    )
    op.create_index("ix_devices_status", "devices", ["status"])

    # --- device_tokens ---
    op.create_table(
        "device_tokens",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("device_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("token_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_device_tokens_device_id"),
    )
    op.create_index("ix_device_tokens_device_id", "device_tokens", ["device_id"])
    op.create_index("ix_device_tokens_token_hash", "device_tokens", ["token_hash"])

    # --- device_config ---
    op.create_table(
        "device_config",
        sa.Column(
            "device_id",
            UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("api_base_url", sa.Text(), nullable=True),
        sa.Column(
            "capture_mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'WHATSAPP_ONLY'"),
        ),
        sa.Column(
            "poll_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("300"),
        ),
        sa.Column(
            "parser_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_device_config_device_id"),
    )


def downgrade() -> None:
    op.drop_table("device_config")

    op.drop_index("ix_device_tokens_token_hash", table_name="device_tokens")
    op.drop_index("ix_device_tokens_device_id", table_name="device_tokens")
    op.drop_table("device_tokens")

    op.drop_index("ix_devices_status", table_name="devices")
    op.drop_constraint("uq_devices_device_uuid", "devices", type_="unique")
    op.drop_table("devices")
