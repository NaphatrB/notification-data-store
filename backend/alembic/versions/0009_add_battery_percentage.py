"""add battery percentage to devices

Revision ID: 0009
Revises: 0008
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("battery_percentage", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("devices", "battery_percentage")
