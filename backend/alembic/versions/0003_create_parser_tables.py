"""create parser tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- parser_offsets ---
    op.create_table(
        "parser_offsets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("parser_name", sa.Text(), nullable=False),
        sa.Column("last_seq", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint(
        "uq_parser_offsets_parser_name", "parser_offsets", ["parser_name"]
    )

    # --- structured_prices ---
    op.create_table(
        "structured_prices",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("raw_event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("supplier", sa.Text(), nullable=True),
        sa.Column("product_grade", sa.Text(), nullable=True),
        sa.Column("size", sa.Text(), nullable=True),
        sa.Column("quantity_kg", sa.Numeric(), nullable=True),
        sa.Column("price_per_kg", sa.Numeric(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("total_kg", sa.Numeric(), nullable=True),
        sa.Column(
            "event_timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("llm_raw_response", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_structured_prices_raw_event_id",
        "structured_prices",
        ["raw_event_id"],
    )
    op.create_index(
        "ix_structured_prices_seq",
        "structured_prices",
        ["seq"],
    )

    # --- pricing_dead_letter ---
    op.create_table(
        "pricing_dead_letter",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("raw_event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("llm_raw_response", JSONB(), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_pricing_dead_letter_raw_event_id",
        "pricing_dead_letter",
        ["raw_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pricing_dead_letter_raw_event_id", table_name="pricing_dead_letter")
    op.drop_table("pricing_dead_letter")

    op.drop_index("ix_structured_prices_seq", table_name="structured_prices")
    op.drop_index("ix_structured_prices_raw_event_id", table_name="structured_prices")
    op.drop_table("structured_prices")

    op.drop_constraint("uq_parser_offsets_parser_name", "parser_offsets", type_="unique")
    op.drop_table("parser_offsets")
