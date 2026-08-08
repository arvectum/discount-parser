from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import xlsxwriter
from python_calamine import CalamineWorkbook
from sqlalchemy import select

from src.core.classification import classify_offer
from src.modules.offers.models import ClassificationRule, ManualOverride, Offer
from src.modules.xlsx.service import export_offers_xlsx, import_offer_corrections
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime


@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "xlsx.db"
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_export_contains_expected_sheets(sqlite_db: Path, tmp_path: Path) -> None:
    with create_session() as session:
        session.add_all(
            [
                Offer(title="active", status="ready", discount_percent=Decimal("20")),
                Offer(title="review", status="needs_review", discount_percent=Decimal("30")),
                Offer(title="published", status="published", discount_percent=Decimal("40")),
                Offer(title="expired", status="expired", discount_percent=Decimal("50")),
            ]
        )
        session.commit()

    path = export_offers_xlsx(tmp_path / "offers.xlsx")
    workbook = CalamineWorkbook.from_path(str(path))
    assert set(workbook.sheet_names) == {"active", "needs_review", "published", "expired", "sources"}

    review_rows = workbook.get_sheet_by_name("needs_review").to_python()
    headers = review_rows[0]
    assert "id" in headers
    assert "category" in headers
    assert "subcategory" in headers


def test_import_applies_override_creates_rule_and_marks_ready(sqlite_db: Path, tmp_path: Path) -> None:
    with create_session() as session:
        offer = Offer(
            title="Pampers Premium Care скидка 30%",
            status="needs_review",
            merchant="Shop",
            category="Другое",
            subcategory="Не определено",
            discount_percent=Decimal("30"),
        )
        session.add(offer)
        session.commit()
        offer_id = offer.id

    correction_path = tmp_path / "correction.xlsx"
    workbook = xlsxwriter.Workbook(str(correction_path), {"strings_to_formulas": False})
    sheet = workbook.add_worksheet("needs_review")
    sheet.write_row(0, 0, ["id", "category", "subcategory"])
    sheet.write_row(1, 0, [offer_id, "Детские товары", "Подгузники"])
    workbook.close()

    report = import_offer_corrections(correction_path)
    assert report.rows_seen == 1
    assert report.rows_changed == 1
    assert report.overrides_written == 2
    assert report.rules_created == 1

    with create_session() as session:
        offer = session.get(Offer, offer_id)
        overrides = session.scalars(select(ManualOverride).where(ManualOverride.offer_id == offer_id)).all()
        rules = session.scalars(select(ClassificationRule)).all()

        assert offer.category == "Детские товары"
        assert offer.subcategory == "Подгузники"
        assert offer.status == "ready"
        assert {row.field_name for row in overrides} == {"category", "subcategory"}
        assert len(rules) == 1
        assert rules[0].match_key == "title"
        assert rules[0].match_value == offer.title

        classification = classify_offer(
            session,
            title=offer.title,
            merchant="Another Shop",
        )
        assert classification.category == "Детские товары"
        assert classification.subcategory == "Подгузники"
        assert classification.reason.startswith("rule:")
