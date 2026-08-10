"""Add geographic fields to offers and publication filters.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    offer_columns = _columns(bind, "offers")
    if offer_columns:
        with op.batch_alter_table("offers") as batch:
            if "city" not in offer_columns:
                batch.add_column(sa.Column("city", sa.String(length=255)))
            if "region" not in offer_columns:
                batch.add_column(sa.Column("region", sa.String(length=255)))
        indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("offers")}
        if "ix_offers_geo" not in indexes:
            op.create_index("ix_offers_geo", "offers", ["region", "city"])

    filter_columns = _columns(bind, "publish_filters")
    if filter_columns:
        with op.batch_alter_table("publish_filters") as batch:
            if "city" not in filter_columns:
                batch.add_column(sa.Column("city", sa.String(length=255)))
            if "region" not in filter_columns:
                batch.add_column(sa.Column("region", sa.String(length=255)))


def downgrade() -> None:
    bind = op.get_bind()
    if "offers" in sa.inspect(bind).get_table_names():
        indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("offers")}
        if "ix_offers_geo" in indexes:
            op.drop_index("ix_offers_geo", table_name="offers")
        columns = _columns(bind, "offers")
        with op.batch_alter_table("offers") as batch:
            if "city" in columns:
                batch.drop_column("city")
            if "region" in columns:
                batch.drop_column("region")

    if "publish_filters" in sa.inspect(bind).get_table_names():
        columns = _columns(bind, "publish_filters")
        with op.batch_alter_table("publish_filters") as batch:
            if "city" in columns:
                batch.drop_column("city")
            if "region" in columns:
                batch.drop_column("region")
