"""Repair nullable legacy source-registry rows after upgrades.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older customer databases may contain NULLs in fields that are now treated
    # as required by the source-registry UI.  Rendering those values through
    # html.escape() raised AttributeError and turned the whole page into HTTP
    # 500.  Repair the durable data during the normal installer `migrate` step
    # so upgraded installations become usable before the web panel starts.
    op.execute(
        """
        UPDATE registered_sources
        SET
            key = COALESCE(NULLIF(key, ''), 'legacy-source-' || id),
            name = COALESCE(NULLIF(name, ''), NULLIF(key, ''), 'Источник #' || id),
            platform = CASE
                WHEN platform IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other') THEN platform
                ELSE 'other'
            END,
            source_type = COALESCE(NULLIF(source_type, ''), 'other'),
            url = COALESCE(url, ''),
            collector_type = COALESCE(NULLIF(collector_type, ''), 'legacy_adapter'),
            network_policy = CASE
                WHEN network_policy IN ('auto','direct','proxy','system') THEN network_policy
                ELSE 'auto'
            END,
            priority = COALESCE(priority, 50),
            trust_level = CASE
                WHEN trust_level IN ('official','verified','community','aggregator','unknown') THEN trust_level
                ELSE 'unknown'
            END,
            check_interval_minutes = COALESCE(check_interval_minutes, 120),
            enabled = COALESCE(enabled, 0),
            status = CASE
                WHEN status IN ('healthy','degraded','blocked','requires_credentials','disabled','unknown') THEN status
                ELSE 'unknown'
            END,
            failure_count = COALESCE(failure_count, 0)
        WHERE
            key IS NULL OR key = '' OR name IS NULL OR name = '' OR
            platform IS NULL OR source_type IS NULL OR source_type = '' OR
            url IS NULL OR collector_type IS NULL OR collector_type = '' OR
            network_policy IS NULL OR priority IS NULL OR trust_level IS NULL OR
            check_interval_minutes IS NULL OR enabled IS NULL OR status IS NULL OR
            failure_count IS NULL
        """
    )

    op.execute(
        """
        UPDATE source_candidates
        SET
            platform = CASE
                WHEN platform IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other') THEN platform
                ELSE 'other'
            END,
            url = COALESCE(url, ''),
            discovered_by = COALESCE(NULLIF(discovered_by, ''), 'legacy'),
            status = CASE
                WHEN status IN ('new','approved','rejected','ignored','invalid') THEN status
                ELSE 'new'
            END,
            confidence = COALESCE(confidence, 0.0)
        WHERE platform IS NULL OR url IS NULL OR discovered_by IS NULL OR
              status IS NULL OR confidence IS NULL
        """
    )

    op.execute(
        """
        UPDATE source_keywords
        SET
            keyword = COALESCE(NULLIF(keyword, ''), 'legacy-keyword-' || id),
            normalized_keyword = COALESCE(NULLIF(normalized_keyword, ''), 'legacy-keyword-' || id),
            kind = CASE
                WHEN kind IN ('strong_positive','positive','negative','merchant','promo_code','price','custom') THEN kind
                ELSE 'custom'
            END,
            enabled = COALESCE(enabled, 0),
            priority = COALESCE(priority, 50)
        WHERE keyword IS NULL OR keyword = '' OR normalized_keyword IS NULL OR
              normalized_keyword = '' OR kind IS NULL OR enabled IS NULL OR priority IS NULL
        """
    )


def downgrade() -> None:
    # Data repair is intentionally irreversible: restoring NULLs would recreate
    # the customer-facing crash this migration fixes.
    pass
