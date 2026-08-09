from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class OfferStatus(StrEnum):
    NEW = "new"
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    EXPIRED = "expired"
    REJECTED = "rejected"


class OfferType(StrEnum):
    PROMO = "promo"
    DISCOUNT = "discount"
    CASHBACK = "cashback"
    DELIVERY = "delivery"
    OTHER = "other"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), default="website", nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (
        CheckConstraint("offer_type IN ('promo','discount','cashback','delivery','other')", name="ck_offers_offer_type"),
        CheckConstraint("status IN ('new','ready','needs_review','published','expired','rejected')", name="ck_offers_status"),
        CheckConstraint("geo_scope IN ('all_russia','region','city','unknown')", name="ck_offers_geo_scope"),
        Index("ix_offers_status", "status"),
        Index("ix_offers_category", "category", "subcategory"),
        Index("ix_offers_geo", "region", "city"),
        Index("ix_offers_geo_scope", "geo_scope"),
        Index("ix_offers_valid_until", "valid_until"),
        Index("ix_offers_canonical_url", "canonical_url"),
        Index("ix_offers_fingerprint", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_type: Mapped[str] = mapped_column(String(32), default=OfferType.OTHER.value, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=OfferStatus.NEW.value, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    display_title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    merchant: Mapped[str | None] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(255))
    subcategory: Mapped[str | None] = mapped_column(String(255))
    geo_scope: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    city: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(255))
    conditions: Mapped[str | None] = mapped_column(Text)
    max_discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_order_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    promo_code: Mapped[str | None] = mapped_column(String(255))
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    new_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    cashback_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    cashback_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    delivery_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    observations: Mapped[list[OfferSourceObservation]] = relationship(back_populates="offer", cascade="all, delete-orphan")
    overrides: Mapped[list[ManualOverride]] = relationship(back_populates="offer", cascade="all, delete-orphan")
    publications: Mapped[list[Publication]] = relationship(back_populates="offer", cascade="all, delete-orphan")


class OfferSourceObservation(Base):
    __tablename__ = "offer_source_observations"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_observation_source_external_id"),
        Index("ix_observations_offer_source", "offer_id", "source_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_title: Mapped[str | None] = mapped_column(Text)
    raw_payload_json: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    offer: Mapped[Offer] = relationship(back_populates="observations")
    source: Mapped[Source] = relationship()


class ParseRun(Base):
    __tablename__ = "parse_runs"
    __table_args__ = (CheckConstraint("status IN ('running','success','partial','failed')", name="ck_parse_runs_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class ClassificationRule(Base):
    __tablename__ = "classification_rules"
    __table_args__ = (Index("ix_classification_rules_priority", "enabled", "priority"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    match_key: Mapped[str] = mapped_column(String(255), nullable=False)
    match_value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManualOverride(Base):
    __tablename__ = "manual_overrides"
    __table_args__ = (UniqueConstraint("offer_id", "field_name", name="uq_manual_override_offer_field"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    offer: Mapped[Offer] = relationship(back_populates="overrides")


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint("offer_id", "channel_id", name="uq_publication_offer_channel"),
        CheckConstraint("status IN ('pending','published','failed','skipped')", name="ck_publications_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_message_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    template_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    offer: Mapped[Offer] = relationship(back_populates="publications")


class PublishFilter(Base):
    __tablename__ = "publish_filters"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    category: Mapped[str | None] = mapped_column(String(255))
    subcategory: Mapped[str | None] = mapped_column(String(255))
    offer_type: Mapped[str | None] = mapped_column(String(32))
    merchant: Mapped[str | None] = mapped_column(String(255))
    source_key: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(255))
    max_posts_per_cycle: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
