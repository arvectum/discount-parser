from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import xlsxwriter
from python_calamine import CalamineWorkbook
from sqlalchemy import select

from src.jobs.status import get_source_run_statuses
from src.modules.offers.models import ClassificationRule, Offer
from src.modules.offers.repository import OfferRepository
from src.shared.db import create_session

OFFER_SHEETS = ("active", "needs_review", "published", "expired")
EDITABLE_COLUMNS = {"category", "subcategory"}

OFFER_HEADERS = [
    "id",
    "status",
    "offer_type",
    "title",
    "merchant",
    "brand",
    "category",
    "subcategory",
    "discount_percent",
    "discount_amount",
    "promo_code",
    "old_price",
    "new_price",
    "cashback_percent",
    "cashback_amount",
    "delivery_price",
    "currency",
    "valid_from",
    "valid_until",
    "canonical_url",
    "image_url",
    "first_seen_at",
    "last_seen_at",
]


@dataclass(slots=True)
class ImportReport:
    rows_seen: int = 0
    rows_changed: int = 0
    overrides_written: int = 0
    rules_created: int = 0
    rows_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _excel_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _offer_row(offer: Offer) -> list[object]:
    return [_excel_value(getattr(offer, column)) for column in OFFER_HEADERS]


def _write_offer_sheet(workbook: xlsxwriter.Workbook, name: str, offers: list[Offer]) -> None:
    sheet = workbook.add_worksheet(name)
    header = workbook.add_format({"bold": True, "bg_color": "#E5E7EB", "border": 1})
    editable = workbook.add_format({"bg_color": "#FFF2CC", "border": 1})
    body = workbook.add_format({"border": 1})
    percent = workbook.add_format({"border": 1, "num_format": "0.00"})

    for col, column in enumerate(OFFER_HEADERS):
        sheet.write(0, col, column, header)

    for row_index, offer in enumerate(offers, start=1):
        values = _offer_row(offer)
        for col, value in enumerate(values):
            column = OFFER_HEADERS[col]
            cell_format = editable if column in EDITABLE_COLUMNS else body
            if column in {"discount_percent", "cashback_percent"} and value is not None:
                cell_format = percent
            sheet.write(row_index, col, value, cell_format)

    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(0, len(offers)), len(OFFER_HEADERS) - 1)
    widths = {
        "id": 10,
        "status": 14,
        "offer_type": 14,
        "title": 42,
        "merchant": 24,
        "brand": 20,
        "category": 22,
        "subcategory": 24,
        "promo_code": 18,
        "canonical_url": 45,
        "image_url": 45,
        "valid_from": 24,
        "valid_until": 24,
        "first_seen_at": 24,
        "last_seen_at": 24,
    }
    for col, column in enumerate(OFFER_HEADERS):
        sheet.set_column(col, col, widths.get(column, 16))


def export_offers_xlsx(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with create_session() as session:
        all_offers = session.scalars(select(Offer).order_by(Offer.id)).all()
        sheets = {
            "active": [offer for offer in all_offers if offer.status in {"new", "ready"}],
            "needs_review": [offer for offer in all_offers if offer.status == "needs_review"],
            "published": [offer for offer in all_offers if offer.status == "published"],
            "expired": [offer for offer in all_offers if offer.status == "expired"],
        }
    source_statuses = get_source_run_statuses()

    workbook = xlsxwriter.Workbook(
        str(destination),
        {"strings_to_formulas": False, "strings_to_urls": False},
    )
    try:
        workbook.set_properties({"title": "Discount Parser offers export"})
        for name in OFFER_SHEETS:
            _write_offer_sheet(workbook, name, sheets[name])

        source_sheet = workbook.add_worksheet("sources")
        source_headers = [
            "source_key",
            "source_name",
            "enabled",
            "last_status",
            "last_started_at",
            "last_finished_at",
            "last_success_at",
            "last_error",
            "fetched_count",
            "new_count",
            "updated_count",
        ]
        header = workbook.add_format({"bold": True, "bg_color": "#E5E7EB", "border": 1})
        body = workbook.add_format({"border": 1})
        for col, value in enumerate(source_headers):
            source_sheet.write(0, col, value, header)
        for row_index, status in enumerate(source_statuses, start=1):
            values = [
                status.source_key,
                status.source_name,
                status.enabled,
                status.last_status,
                _excel_value(status.last_started_at),
                _excel_value(status.last_finished_at),
                _excel_value(status.last_success_at),
                status.last_error,
                status.fetched_count,
                status.new_count,
                status.updated_count,
            ]
            for col, value in enumerate(values):
                source_sheet.write(row_index, col, value, body)
        source_sheet.freeze_panes(1, 0)
        source_sheet.autofilter(0, 0, max(0, len(source_statuses)), len(source_headers) - 1)
        source_sheet.set_column(0, len(source_headers) - 1, 18)
        source_sheet.set_column(1, 1, 28)
        source_sheet.set_column(7, 7, 50)
    finally:
        workbook.close()
    return destination


def _string(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _offer_has_benefit(offer: Offer) -> bool:
    return any(
        value is not None
        for value in (
            offer.discount_percent,
            offer.discount_amount,
            offer.cashback_percent,
            offer.cashback_amount,
            offer.delivery_price,
        )
    ) or bool(offer.promo_code)


def _create_conservative_rule(session, offer: Offer) -> bool:
    if not offer.category or not offer.title or len(offer.title.strip()) < 6:
        return False
    existing = session.scalar(
        select(ClassificationRule).where(
            ClassificationRule.match_key == "title",
            ClassificationRule.match_value == offer.title,
            ClassificationRule.category == offer.category,
            ClassificationRule.subcategory == offer.subcategory,
            ClassificationRule.enabled.is_(True),
        )
    )
    if existing is not None:
        return False
    session.add(
        ClassificationRule(
            match_key="title",
            match_value=offer.title,
            category=offer.category,
            subcategory=offer.subcategory,
            source="xlsx_manual",
            priority=200,
            enabled=True,
        )
    )
    return True


def import_offer_corrections(path: str | Path, *, create_rules: bool = True) -> ImportReport:
    report = ImportReport()
    workbook = CalamineWorkbook.from_path(str(path))

    with create_session() as session:
        repo = OfferRepository(session)
        for sheet_name in OFFER_SHEETS:
            if sheet_name not in workbook.sheet_names:
                continue
            rows = workbook.get_sheet_by_name(sheet_name).to_python()
            if not rows:
                continue
            headers = [str(value).strip() if value is not None else "" for value in rows[0]]
            index = {header: position for position, header in enumerate(headers) if header}
            if "id" not in index:
                report.errors.append(f"{sheet_name}: missing id column")
                continue
            if not EDITABLE_COLUMNS.issubset(index):
                report.errors.append(f"{sheet_name}: missing editable columns")
                continue

            for row_number, row in enumerate(rows[1:], start=2):
                if not row or index["id"] >= len(row) or row[index["id"]] in (None, ""):
                    continue
                report.rows_seen += 1
                try:
                    offer_id = int(float(row[index["id"]]))
                except (TypeError, ValueError):
                    report.rows_skipped += 1
                    report.errors.append(f"{sheet_name}!{row_number}: invalid id")
                    continue

                offer = session.get(Offer, offer_id)
                if offer is None:
                    report.rows_skipped += 1
                    report.errors.append(f"{sheet_name}!{row_number}: offer {offer_id} not found")
                    continue

                changed = False
                for field_name in ("category", "subcategory"):
                    position = index[field_name]
                    value = _string(row[position] if position < len(row) else None)
                    if value is None or value == getattr(offer, field_name):
                        continue
                    repo.set_manual_override(offer, field_name, value, source="xlsx")
                    report.overrides_written += 1
                    changed = True

                if not changed:
                    report.rows_skipped += 1
                    continue

                report.rows_changed += 1
                if offer.status == "needs_review" and offer.category and offer.category != "Другое" and _offer_has_benefit(offer):
                    offer.status = "ready"
                if create_rules and _create_conservative_rule(session, offer):
                    report.rules_created += 1

        session.commit()

    return report
