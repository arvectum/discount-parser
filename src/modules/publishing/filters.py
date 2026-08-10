from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from src.modules.offers.models import PublishFilter
from src.shared.db import create_session

DEFAULT_FILTER_NAME = "telegram-default"


def get_or_create_default_filter(*, min_discount_percent: int = 20) -> PublishFilter:
    with create_session() as session:
        row = session.scalar(select(PublishFilter).where(PublishFilter.name == DEFAULT_FILTER_NAME))
        if row is None:
            row = PublishFilter(
                name=DEFAULT_FILTER_NAME,
                enabled=False,
                min_discount_percent=Decimal(min_discount_percent),
                max_posts_per_cycle=10,
            )
            session.add(row)
            session.commit()
        return row


def update_default_filter(**values) -> PublishFilter:
    allowed = {
        "enabled",
        "min_discount_percent",
        "category",
        "subcategory",
        "offer_type",
        "merchant",
        "source_key",
        "city",
        "region",
        "max_posts_per_cycle",
    }
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown filter fields: {sorted(unknown)}")

    with create_session() as session:
        row = session.scalar(select(PublishFilter).where(PublishFilter.name == DEFAULT_FILTER_NAME))
        if row is None:
            row = PublishFilter(name=DEFAULT_FILTER_NAME, enabled=False, max_posts_per_cycle=10)
            session.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        session.commit()
        return row
