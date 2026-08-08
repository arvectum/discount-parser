from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


PLATFORMS = ("website", "promo_aggregator", "telegram", "vk", "dzen", "rutube", "other")
SOURCE_STATUSES = ("healthy", "degraded", "blocked", "requires_credentials", "disabled", "unknown")
CANDIDATE_STATUSES = ("new", "approved", "rejected", "ignored", "invalid")
ITEM_STATUSES = ("new", "processed", "ignored", "needs_review", "failed")
TRUST_LEVELS = ("official", "verified", "community", "aggregator", "unknown")
KEYWORD_KINDS = ("strong_positive", "positive", "negative", "merchant", "promo_code", "price", "custom")


class RegisteredSource(Base):
    __tablename__ = "registered_sources"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other')",
            name="ck_registered_sources_platform",
        ),
        CheckConstraint(
            "status IN ('healthy','degraded','blocked','requires_credentials','disabled','unknown')",
            name="ck_registered_sources_status",
        ),
        CheckConstraint(
            "trust_level IN ('official','verified','community','aggregator','unknown')",
            name="ck_registered_sources_trust",
        ),
        Index("ix_registered_sources_platform_enabled", "platform", "enabled"),
        Index("ix_registered_sources_merchant", "merchant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), default="other", nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    merchant: Mapped[str | None] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(255))
    collector_type: Mapped[str] = mapped_column(String(80), nullable=False)
    auth_profile: Mapped[str | None] = mapped_column(String(80))
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    trust_level: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_cursor: Mapped[str | None] = mapped_column(String(255))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    items: Mapped[list[SourceItem]] = relationship(back_populates="source", cascade="all, delete-orphan")
    keyword_links: Mapped[list[SourceKeywordLink]] = relationship(back_populates="source", cascade="all, delete-orphan")


class SourceKeyword(Base):
    __tablename__ = "source_keywords"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('strong_positive','positive','negative','merchant','promo_code','price','custom')",
            name="ck_source_keywords_kind",
        ),
        UniqueConstraint("normalized_keyword", "kind", "merchant", name="uq_source_keyword_scope"),
        Index("ix_source_keywords_enabled_priority", "enabled", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="positive", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(255))
    subcategory: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    source_links: Mapped[list[SourceKeywordLink]] = relationship(back_populates="keyword", cascade="all, delete-orphan")


class SourceKeywordLink(Base):
    __tablename__ = "source_keyword_links"
    __table_args__ = (UniqueConstraint("source_id", "keyword_id", name="uq_source_keyword_link"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("registered_sources.id", ondelete="CASCADE"), nullable=False)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("source_keywords.id", ondelete="CASCADE"), nullable=False)

    source: Mapped[RegisteredSource] = relationship(back_populates="keyword_links")
    keyword: Mapped[SourceKeyword] = relationship(back_populates="source_links")


class SourceCandidate(Base):
    __tablename__ = "source_candidates"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other')",
            name="ck_source_candidates_platform",
        ),
        CheckConstraint(
            "status IN ('new','approved','rejected','ignored','invalid')",
            name="ck_source_candidates_status",
        ),
        UniqueConstraint("platform", "url", name="uq_source_candidate_platform_url"),
        Index("ix_source_candidates_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    discovered_by: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    discovery_query: Mapped[str | None] = mapped_column(Text)
    merchant: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[str | None] = mapped_column(Text)


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('new','processed','ignored','needs_review','failed')",
            name="ck_source_items_status",
        ),
        UniqueConstraint("registered_source_id", "external_id", name="uq_source_item_source_external"),
        Index("ix_source_items_source_published", "registered_source_id", "published_at"),
        Index("ix_source_items_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registered_source_id: Mapped[int] = mapped_column(ForeignKey("registered_sources.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author: Mapped[str | None] = mapped_column(String(255))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_payload_json: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    processing_error: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    source: Mapped[RegisteredSource] = relationship(back_populates="items")
