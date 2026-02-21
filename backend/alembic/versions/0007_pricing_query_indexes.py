"""add pricing query indexes on structured_prices

Revision ID: 0007
Revises: 0006
Create Date: 2026-02-21

Adds indexes for supplier, currency, price_per_kg, parser_version.
seq and raw_event_id indexes already exist from migration 0003.
"""
from typing import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_structured_prices_supplier",
        "structured_prices",
        ["supplier"],
    )
    op.create_index(
        "ix_structured_prices_currency",
        "structured_prices",
        ["currency"],
    )
    op.create_index(
        "ix_structured_prices_price_per_kg",
        "structured_prices",
        ["price_per_kg"],
    )
    op.create_index(
        "ix_structured_prices_parser_version",
        "structured_prices",
        ["parser_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_structured_prices_parser_version", table_name="structured_prices")
    op.drop_index("ix_structured_prices_price_per_kg", table_name="structured_prices")
    op.drop_index("ix_structured_prices_currency", table_name="structured_prices")
    op.drop_index("ix_structured_prices_supplier", table_name="structured_prices")
