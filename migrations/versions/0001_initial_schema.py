"""Initial Discount Parser persistence schema.

Revision ID: 0001
Revises: None
"""

from alembic import op

from src.modules.offers import models as offer_models  # noqa: F401
from src.shared.db import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
