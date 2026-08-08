from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.normalization import normalize_text
from src.modules.offers.models import ClassificationRule, Offer


@dataclass(frozen=True, slots=True)
class Classification:
    category: str
    subcategory: str | None = None
    reason: str = "fallback"


def _manual_fields(offer: Offer | None) -> set[str]:
    if offer is None:
        return set()
    return {override.field_name for override in offer.overrides}


def classify_offer(
    session: Session,
    *,
    title: str,
    merchant: str | None,
    brand: str | None = None,
    offer: Offer | None = None,
    taxonomy_path: str | Path = "config/taxonomy.yaml",
) -> Classification:
    protected = _manual_fields(offer)
    if offer is not None and "category" in protected and offer.category:
        return Classification(offer.category, offer.subcategory, "manual_override")

    haystack = normalize_text(" ".join(x for x in [merchant, brand, title] if x))

    rules = session.scalars(
        select(ClassificationRule)
        .where(ClassificationRule.enabled.is_(True))
        .order_by(ClassificationRule.priority.desc(), ClassificationRule.id.asc())
    ).all()
    for rule in rules:
        match_value = normalize_text(rule.match_value)
        if not match_value:
            continue
        if rule.match_key in {"merchant", "brand", "title", "contains"}:
            target = {
                "merchant": normalize_text(merchant),
                "brand": normalize_text(brand),
                "title": normalize_text(title),
                "contains": haystack,
            }[rule.match_key]
            if match_value in target:
                return Classification(rule.category, rule.subcategory, f"rule:{rule.id}")

    data = yaml.safe_load(Path(taxonomy_path).read_text(encoding="utf-8")) or {}
    for category in data.get("categories", []):
        name = str(category["name"])
        for keyword in category.get("keywords", []):
            if normalize_text(str(keyword)) in haystack:
                return Classification(name, None, f"keyword:{keyword}")

    return Classification("Другое", "Не определено", "fallback")
