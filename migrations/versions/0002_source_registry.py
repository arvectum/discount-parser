"""Add multi-platform source registry.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _missing(bind, table_name: str) -> bool:
    return table_name not in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if _missing(bind, "registered_sources"):
        op.create_table(
            "registered_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("key", sa.String(length=120), nullable=False, unique=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False, server_default="other"),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("external_id", sa.String(length=255)),
            sa.Column("merchant", sa.String(length=255)),
            sa.Column("brand", sa.String(length=255)),
            sa.Column("collector_type", sa.String(length=80), nullable=False),
            sa.Column("auth_profile", sa.String(length=80)),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("trust_level", sa.String(length=32), nullable=False, server_default="unknown"),
            sa.Column("check_interval_minutes", sa.Integer(), nullable=False, server_default="120"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="unknown"),
            sa.Column("last_cursor", sa.String(length=255)),
            sa.Column("last_checked_at", sa.DateTime(timezone=True)),
            sa.Column("last_success_at", sa.DateTime(timezone=True)),
            sa.Column("last_error_at", sa.DateTime(timezone=True)),
            sa.Column("last_error", sa.Text()),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("platform IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other')", name="ck_registered_sources_platform"),
            sa.CheckConstraint("status IN ('healthy','degraded','blocked','requires_credentials','disabled','unknown')", name="ck_registered_sources_status"),
            sa.CheckConstraint("trust_level IN ('official','verified','community','aggregator','unknown')", name="ck_registered_sources_trust"),
        )
        op.create_index("ix_registered_sources_platform_enabled", "registered_sources", ["platform", "enabled"])
        op.create_index("ix_registered_sources_merchant", "registered_sources", ["merchant"])

    if _missing(bind, "source_keywords"):
        op.create_table(
            "source_keywords",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("keyword", sa.String(length=255), nullable=False),
            sa.Column("normalized_keyword", sa.String(length=255), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False, server_default="positive"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("merchant", sa.String(length=255)),
            sa.Column("category", sa.String(length=255)),
            sa.Column("subcategory", sa.String(length=255)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("kind IN ('strong_positive','positive','negative','merchant','promo_code','price','custom')", name="ck_source_keywords_kind"),
            sa.UniqueConstraint("normalized_keyword", "kind", "merchant", name="uq_source_keyword_scope"),
        )
        op.create_index("ix_source_keywords_enabled_priority", "source_keywords", ["enabled", "priority"])

    if _missing(bind, "source_candidates"):
        op.create_table(
            "source_candidates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("external_id", sa.String(length=255)),
            sa.Column("name", sa.String(length=255)),
            sa.Column("discovered_by", sa.String(length=80), nullable=False, server_default="manual"),
            sa.Column("discovery_query", sa.Text()),
            sa.Column("merchant", sa.String(length=255)),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("approved_at", sa.DateTime(timezone=True)),
            sa.Column("rejected_at", sa.DateTime(timezone=True)),
            sa.Column("metadata_json", sa.Text()),
            sa.CheckConstraint("platform IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other')", name="ck_source_candidates_platform"),
            sa.CheckConstraint("status IN ('new','approved','rejected','ignored','invalid')", name="ck_source_candidates_status"),
            sa.UniqueConstraint("platform", "url", name="uq_source_candidate_platform_url"),
        )
        op.create_index("ix_source_candidates_status", "source_candidates", ["status"])

    if _missing(bind, "source_keyword_links"):
        op.create_table(
            "source_keyword_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("registered_sources.id", ondelete="CASCADE"), nullable=False),
            sa.Column("keyword_id", sa.Integer(), sa.ForeignKey("source_keywords.id", ondelete="CASCADE"), nullable=False),
            sa.UniqueConstraint("source_id", "keyword_id", name="uq_source_keyword_link"),
        )

    if _missing(bind, "source_items"):
        op.create_table(
            "source_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("registered_source_id", sa.Integer(), sa.ForeignKey("registered_sources.id", ondelete="CASCADE"), nullable=False),
            sa.Column("external_id", sa.String(length=255)),
            sa.Column("url", sa.Text()),
            sa.Column("title", sa.Text()),
            sa.Column("text", sa.Text()),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("author", sa.String(length=255)),
            sa.Column("image_url", sa.Text()),
            sa.Column("raw_payload_json", sa.Text()),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="new"),
            sa.Column("processing_error", sa.Text()),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("processing_status IN ('new','processed','ignored','needs_review','failed')", name="ck_source_items_status"),
            sa.UniqueConstraint("registered_source_id", "external_id", name="uq_source_item_source_external"),
        )
        op.create_index("ix_source_items_source_published", "source_items", ["registered_source_id", "published_at"])
        op.create_index("ix_source_items_content_hash", "source_items", ["content_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table in ("source_items", "source_keyword_links", "source_candidates", "source_keywords", "registered_sources"):
        if table in tables:
            op.drop_table(table)
