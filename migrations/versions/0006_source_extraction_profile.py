"""Add source extraction-profile fields.

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("item_selector", sa.Text()), ("title_selector", sa.Text()),
    ("promo_code_selector", sa.Text()), ("promo_code_attribute", sa.String(length=120)),
    ("conditions_selector", sa.Text()), ("valid_until_selector", sa.Text()),
    ("link_selector", sa.Text()), ("reveal_selector", sa.Text()),
    ("reveal_code_attribute", sa.String(length=120)),
)


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("registered_sources")}
    with op.batch_alter_table("registered_sources") as batch:
        for name, column_type in _COLUMNS:
            if name not in existing:
                batch.add_column(sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("registered_sources")}
    with op.batch_alter_table("registered_sources") as batch:
        for name, _ in reversed(_COLUMNS):
            if name in existing:
                batch.drop_column(name)
