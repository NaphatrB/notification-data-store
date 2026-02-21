"""add partial unique index: one active token per device

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-21

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "one_active_token_per_device",
        "device_tokens",
        ["device_id"],
        unique=True,
        postgresql_where="revoked_at IS NULL",
    )


def downgrade() -> None:
    op.drop_index("one_active_token_per_device", table_name="device_tokens")
