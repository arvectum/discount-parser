"""Add optional per-source image extraction profiles.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_image_profiles",
        sa.Column(
            "registered_source_id",
            sa.Integer(),
            sa.ForeignKey("registered_sources.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("image_selector", sa.Text(), nullable=True),
        sa.Column("image_attribute", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("source_image_profiles")
