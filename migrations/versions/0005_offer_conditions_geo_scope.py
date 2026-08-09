"""Add geo scope and structured offer conditions.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind, "offers")
    if columns:
        with op.batch_alter_table("offers") as batch:
            if "geo_scope" not in columns:
                batch.add_column(sa.Column("geo_scope", sa.String(length=32), nullable=False, server_default="unknown"))
            if "conditions" not in columns:
                batch.add_column(sa.Column("conditions", sa.Text()))
            if "max_discount_amount" not in columns:
                batch.add_column(sa.Column("max_discount_amount", sa.Numeric(14, 2)))
            if "min_order_amount" not in columns:
                batch.add_column(sa.Column("min_order_amount", sa.Numeric(14, 2)))
        indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("offers")}
        if "ix_offers_geo_scope" not in indexes:
            op.create_index("ix_offers_geo_scope", "offers", ["geo_scope"])


def downgrade() -> None:
    bind = op.get_bind()
    if "offers" not in sa.inspect(bind).get_table_names():
        return
    indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("offers")}
    if "ix_offers_geo_scope" in indexes:
        op.drop_index("ix_offers_geo_scope", table_name="offers")
    columns = _columns(bind, "offers")
    with op.batch_alter_table("offers") as batch:
        for name in ("min_order_amount", "max_discount_amount", "conditions", "geo_scope"):
            if name in columns:
                batch.drop_column(name)
