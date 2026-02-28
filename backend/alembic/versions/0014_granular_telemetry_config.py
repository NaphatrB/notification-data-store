"""add granular telemetry config

Revision ID: 0014
Revises: 0013
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('device_config', sa.Column('collect_battery', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('device_config', sa.Column('collect_temperature', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('device_config', sa.Column('collect_location', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('device_config', 'collect_location')
    op.drop_column('device_config', 'collect_temperature')
    op.drop_column('device_config', 'collect_battery')
