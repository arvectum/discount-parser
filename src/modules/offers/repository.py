from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.offers.models import ManualOverride, Offer, Publication


class OfferRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **values) -> Offer:
        offer = Offer(**values)
        self.session.add(offer)
        self.session.flush()
        return offer

    def get(self, offer_id: int) -> Offer | None:
        return self.session.get(Offer, offer_id)

    def update(self, offer: Offer, values: Mapping[str, object]) -> Offer:
        protected = {row.field_name for row in offer.overrides}
        for field_name, value in values.items():
            if field_name in protected:
                continue
            if not hasattr(offer, field_name):
                raise ValueError(f"unknown Offer field: {field_name}")
            setattr(offer, field_name, value)
        self.session.flush()
        return offer

    def set_manual_override(self, offer: Offer, field_name: str, value: str | None, source: str = "manual") -> ManualOverride:
        if not hasattr(offer, field_name):
            raise ValueError(f"unknown Offer field: {field_name}")
        override = self.session.scalar(
            select(ManualOverride).where(
                ManualOverride.offer_id == offer.id,
                ManualOverride.field_name == field_name,
            )
        )
        if override is None:
            override = ManualOverride(offer_id=offer.id, field_name=field_name, value=value, source=source)
            self.session.add(override)
        else:
            override.value = value
            override.source = source
        setattr(offer, field_name, value)
        self.session.flush()
        return override

    def create_publication(self, offer: Offer, channel_id: str, **values) -> Publication:
        publication = Publication(offer_id=offer.id, channel_id=channel_id, **values)
        self.session.add(publication)
        self.session.flush()
        return publication
