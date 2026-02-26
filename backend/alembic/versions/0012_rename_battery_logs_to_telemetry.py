"""rename battery logs to telemetry

Revision ID: 0012
Revises: 0011
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename table
    op.rename_table("device_battery_logs", "device_telemetry_logs")
    
    # Rename primary key constraint
    op.execute("ALTER TABLE device_telemetry_logs RENAME CONSTRAINT device_battery_logs_pkey TO device_telemetry_logs_pkey")
    
    # Rename foreign key constraint
    op.execute("ALTER TABLE device_telemetry_logs RENAME CONSTRAINT device_battery_logs_device_id_fkey TO device_telemetry_logs_device_id_fkey")
    
    # Rename indexes
    op.execute("ALTER INDEX ix_device_battery_logs_created_at RENAME TO ix_device_telemetry_logs_created_at")
    op.execute("ALTER INDEX ix_device_battery_logs_device_id RENAME TO ix_device_telemetry_logs_device_id")


def downgrade() -> None:
    # Rename indexes back
    op.execute("ALTER INDEX ix_device_telemetry_logs_device_id RENAME TO ix_device_battery_logs_device_id")
    op.execute("ALTER INDEX ix_device_telemetry_logs_created_at RENAME TO ix_device_battery_logs_created_at")
    
    # Rename foreign key constraint back
    op.execute("ALTER TABLE device_telemetry_logs RENAME CONSTRAINT device_telemetry_logs_device_id_fkey TO device_battery_logs_device_id_fkey")
    
    # Rename primary key constraint back
    op.execute("ALTER TABLE device_telemetry_logs RENAME CONSTRAINT device_telemetry_logs_pkey TO device_battery_logs_pkey")
    
    # Rename table back
    op.rename_table("device_telemetry_logs", "device_battery_logs")
