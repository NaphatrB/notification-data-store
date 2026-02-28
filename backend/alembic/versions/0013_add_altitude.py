"""add altitude

Revision ID: 0013
Revises: 0012
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("altitude", sa.Float(), nullable=True))
    op.add_column("device_telemetry_logs", sa.Column("altitude", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("device_telemetry_logs", "altitude")
    op.drop_column("devices", "altitude")
