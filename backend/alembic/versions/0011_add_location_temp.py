"""add location and temperature

Revision ID: 0011
Revises: 0010
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add to devices table
    op.add_column("devices", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("devices", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("devices", sa.Column("longitude", sa.Float(), nullable=True))
    
    # Add to device_battery_logs table
    op.add_column("device_battery_logs", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("device_battery_logs", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("device_battery_logs", sa.Column("longitude", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("device_battery_logs", "longitude")
    op.drop_column("device_battery_logs", "latitude")
    op.drop_column("device_battery_logs", "temperature")
    
    op.drop_column("devices", "longitude")
    op.drop_column("devices", "latitude")
    op.drop_column("devices", "temperature")
