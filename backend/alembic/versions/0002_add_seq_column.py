"""add seq column to raw_events

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add seq column as plain BIGINT (temporarily nullable for backfill)
    op.add_column(
        "raw_events",
        sa.Column("seq", sa.BigInteger(), nullable=True),
    )

    # Backfill existing rows ordered by received_at
    op.execute(
        """
        UPDATE raw_events
        SET seq = s.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (ORDER BY received_at) AS rn
            FROM raw_events
        ) s
        WHERE raw_events.id = s.id
        """
    )

    # Now make it NOT NULL
    op.alter_column("raw_events", "seq", nullable=False)

    # Add unique constraint and index
    op.create_unique_constraint("uq_raw_events_seq", "raw_events", ["seq"])
    op.create_index("ix_raw_events_seq", "raw_events", ["seq"])

    # Create a sequence and attach it to the column for auto-increment
    op.execute("CREATE SEQUENCE raw_events_seq_seq OWNED BY raw_events.seq")
    op.execute(
        """
        SELECT setval('raw_events_seq_seq',
                       COALESCE((SELECT MAX(seq) FROM raw_events), 1),
                       COALESCE((SELECT MAX(seq) FROM raw_events) IS NOT NULL, false))
        """
    )
    op.execute(
        """
        ALTER TABLE raw_events ALTER COLUMN seq SET DEFAULT nextval('raw_events_seq_seq')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE raw_events ALTER COLUMN seq DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS raw_events_seq_seq")
    op.drop_index("ix_raw_events_seq", table_name="raw_events")
    op.drop_constraint("uq_raw_events_seq", "raw_events", type_="unique")
    op.drop_column("raw_events", "seq")
