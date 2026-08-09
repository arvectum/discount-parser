"""Add per-source network routing policy.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind, "registered_sources")
    if not columns or "network_policy" in columns:
        return
    with op.batch_alter_table("registered_sources") as batch:
        batch.add_column(sa.Column("network_policy", sa.String(length=16), nullable=False, server_default="auto"))


def downgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind, "registered_sources")
    if "network_policy" in columns:
        with op.batch_alter_table("registered_sources") as batch:
            batch.drop_column("network_policy")
