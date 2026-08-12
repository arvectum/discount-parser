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


def _check_constraints(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {
        str(item["name"])
        for item in inspector.get_check_constraints(table_name)
        if item.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind, "offers")
    checks = _check_constraints(bind, "offers")
    if columns:
        has_geo_scope_check = any(
            "geo_scope" in str(item.get("sqltext") or "")
            for item in sa.inspect(bind).get_check_constraints("offers")
        )
        with op.batch_alter_table("offers") as batch:
            if "geo_scope" not in columns:
                batch.add_column(sa.Column("geo_scope", sa.String(length=32), nullable=False, server_default="unknown"))
            if not has_geo_scope_check:
                batch.create_check_constraint(
                    "ck_offers_geo_scope",
                    "geo_scope IN ('all_russia','region','city','unknown')",
                )
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
    inspector = sa.inspect(bind)
    
    # Drop index first
    indexes = {idx["name"] for idx in inspector.get_indexes("offers")}
    if "ix_offers_geo_scope" in indexes:
        op.drop_index("ix_offers_geo_scope", table_name="offers")
    
    columns = _columns(bind, "offers")
    
    # To fix SQLite "no such column: geo_scope" during table recreation:
    # We must ensure Alembic doesn't try to recreate the CHECK constraint 
    # that refers to geo_scope in the new table.
    
    with op.batch_alter_table("offers", naming_convention={
        "check": "ck_%(table_name)s_%(constraint_name)s",
    }) as batch:
        # Explicitly drop the constraint by name. 
        # Alembic's batch mode will then omit it from the CREATE TABLE of the temp table.
        batch.drop_constraint("ck_offers_geo_scope", type_="check")
        
        for name in ("min_order_amount", "max_discount_amount", "conditions", "geo_scope"):
            if name in columns:
                batch.drop_column(name)

