"""Add optional two-stage website crawl profiles.

Revision ID: 0009
Revises: 0008
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "source_follow_profiles" in inspector.get_table_names():
        return
    op.create_table(
        "source_follow_profiles",
        sa.Column("registered_source_id", sa.Integer(), nullable=False),
        sa.Column("crawl_mode", sa.String(length=32), nullable=False, server_default="direct"),
        sa.Column("listing_item_selector", sa.Text(), nullable=True),
        sa.Column("detail_link_selector", sa.Text(), nullable=True),
        sa.Column("detail_url_contains", sa.Text(), nullable=True),
        sa.Column("merchant_selector", sa.Text(), nullable=True),
        sa.Column("max_detail_pages", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["registered_source_id"], ["registered_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("registered_source_id"),
        sa.CheckConstraint("crawl_mode IN ('direct','follow_internal')", name="ck_source_follow_profiles_mode"),
        sa.CheckConstraint("max_detail_pages BETWEEN 1 AND 500", name="ck_source_follow_profiles_max_pages"),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "source_follow_profiles" in inspector.get_table_names():
        op.drop_table("source_follow_profiles")
