"""add product column to structured_prices

Revision ID: 0008
Revises: 0007
Create Date: 2026-02-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "structured_prices",
        sa.Column("product", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("structured_prices", "product")
