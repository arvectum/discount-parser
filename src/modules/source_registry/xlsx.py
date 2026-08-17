from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import xlsxwriter
from python_calamine import CalamineWorkbook
from sqlalchemy import select

from src.modules.source_registry.models import RegisteredSource, SourceCandidate, SourceKeyword
from src.modules.source_registry.service import add_keyword, create_source, upsert_candidate
from src.shared.db import create_session

SOURCE_HEADERS = [
    "key", "name", "platform", "source_type", "url", "external_id", "merchant", "brand",
    "collector_type", "auth_profile", "priority", "trust_level", "check_interval_minutes", "enabled",
    "item_selector", "title_selector", "promo_code_selector", "promo_code_attribute", "conditions_selector",
    "valid_until_selector", "link_selector", "reveal_selector", "reveal_code_attribute",
    "status", "last_checked_at", "last_success_at", "last_error",
]
CANDIDATE_HEADERS = [
    "id", "platform", "url", "external_id", "name", "merchant", "discovered_by", "discovery_query",
    "status", "confidence", "first_seen_at", "last_seen_at",
]
KEYWORD_HEADERS = [
    "id", "keyword", "kind", "priority", "merchant", "category", "subcategory", "enabled",
]


@dataclass(slots=True)
class RegistryImportReport:
    sources_created: int = 0
    sources_skipped: int = 0
    candidates_created_or_updated: int = 0
    keywords_created: int = 0
    rows_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _value(row, index: dict[str, int], name: str):
    position = index.get(name)
    if position is None or position >= len(row):
        return None
    return row[position]


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(value, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() not in {"0", "false", "no", "нет", "off"}


def _int(value, default: int) -> int:
    if value in (None, ""):
        return default
    return int(float(value))


def export_source_registry_xlsx(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with create_session() as session:
        sources = session.scalars(select(RegisteredSource).order_by(RegisteredSource.platform, RegisteredSource.name)).all()
        candidates = session.scalars(select(SourceCandidate).order_by(SourceCandidate.status, SourceCandidate.id)).all()
        keywords = session.scalars(select(SourceKeyword).order_by(SourceKeyword.kind, SourceKeyword.priority.desc())).all()

    workbook = xlsxwriter.Workbook(str(destination), {"strings_to_formulas": False, "strings_to_urls": False})
    header = workbook.add_format({"bold": True, "bg_color": "#E5E7EB", "border": 1})
    body = workbook.add_format({"border": 1})
    try:
        for sheet_name, headers, rows in (
            ("sources", SOURCE_HEADERS, sources),
            ("candidates", CANDIDATE_HEADERS, candidates),
            ("keywords", KEYWORD_HEADERS, keywords),
        ):
            sheet = workbook.add_worksheet(sheet_name)
            for col, name in enumerate(headers):
                sheet.write(0, col, name, header)
            for row_index, obj in enumerate(rows, start=1):
                for col, name in enumerate(headers):
                    value = getattr(obj, name)
                    if hasattr(value, "isoformat"):
                        value = value.isoformat()
                    sheet.write(row_index, col, value, body)
            sheet.freeze_panes(1, 0)
            sheet.autofilter(0, 0, max(0, len(rows)), len(headers) - 1)
            sheet.set_column(0, len(headers) - 1, 18)
        workbook.get_worksheet_by_name("sources").set_column(SOURCE_HEADERS.index("url"), SOURCE_HEADERS.index("url"), 50)
        workbook.get_worksheet_by_name("candidates").set_column(CANDIDATE_HEADERS.index("url"), CANDIDATE_HEADERS.index("url"), 50)
    finally:
        workbook.close()
    return destination


def import_source_registry_xlsx(path: str | Path) -> RegistryImportReport:
    report = RegistryImportReport()
    workbook = CalamineWorkbook.from_path(str(path))
    with create_session() as session:
        if "sources" in workbook.sheet_names:
            rows = workbook.get_sheet_by_name("sources").to_python()
            if rows:
                headers = [str(v).strip() if v is not None else "" for v in rows[0]]
                index = {name: i for i, name in enumerate(headers) if name}
                required = {"name", "platform", "url", "collector_type"}
                if not required.issubset(index):
                    report.errors.append("sources: required columns name/platform/url/collector_type are missing")
                else:
                    for row_no, row in enumerate(rows[1:], start=2):
                        if not row or not _text(_value(row, index, "url")):
                            continue
                        try:
                            url = _text(_value(row, index, "url")) or ""
                            platform = _text(_value(row, index, "platform")) or ""
                            existing = session.scalar(
                                select(RegisteredSource).where(RegisteredSource.platform == platform, RegisteredSource.url == url)
                            )
                            if existing is not None:
                                report.sources_skipped += 1
                                continue
                            create_source(
                                session,
                                key=_text(_value(row, index, "key")),
                                name=_text(_value(row, index, "name")) or url,
                                platform=platform,
                                source_type=_text(_value(row, index, "source_type")) or "other",
                                url=url,
                                external_id=_text(_value(row, index, "external_id")),
                                merchant=_text(_value(row, index, "merchant")),
                                brand=_text(_value(row, index, "brand")),
                                collector_type=_text(_value(row, index, "collector_type")) or "public_page",
                                auth_profile=_text(_value(row, index, "auth_profile")),
                                item_selector=_text(_value(row, index, "item_selector")),
                                title_selector=_text(_value(row, index, "title_selector")),
                                promo_code_selector=_text(_value(row, index, "promo_code_selector")),
                                promo_code_attribute=_text(_value(row, index, "promo_code_attribute")),
                                conditions_selector=_text(_value(row, index, "conditions_selector")),
                                valid_until_selector=_text(_value(row, index, "valid_until_selector")),
                                link_selector=_text(_value(row, index, "link_selector")),
                                reveal_selector=_text(_value(row, index, "reveal_selector")),
                                reveal_code_attribute=_text(_value(row, index, "reveal_code_attribute")),
                                priority=_int(_value(row, index, "priority"), 50),
                                trust_level=_text(_value(row, index, "trust_level")) or "unknown",
                                check_interval_minutes=_int(_value(row, index, "check_interval_minutes"), 120),
                                enabled=_bool(_value(row, index, "enabled"), True),
                            )
                            report.sources_created += 1
                        except Exception as exc:
                            report.rows_skipped += 1
                            report.errors.append(f"sources!{row_no}: {type(exc).__name__}: {exc}")

        if "candidates" in workbook.sheet_names:
            rows = workbook.get_sheet_by_name("candidates").to_python()
            if rows:
                headers = [str(v).strip() if v is not None else "" for v in rows[0]]
                index = {name: i for i, name in enumerate(headers) if name}
                for row_no, row in enumerate(rows[1:], start=2):
                    url = _text(_value(row, index, "url"))
                    platform = _text(_value(row, index, "platform"))
                    if not url or not platform:
                        continue
                    try:
                        upsert_candidate(
                            session,
                            platform=platform,
                            url=url,
                            external_id=_text(_value(row, index, "external_id")),
                            name=_text(_value(row, index, "name")),
                            merchant=_text(_value(row, index, "merchant")),
                            discovered_by=_text(_value(row, index, "discovered_by")) or "xlsx",
                            discovery_query=_text(_value(row, index, "discovery_query")),
                            confidence=float(_value(row, index, "confidence") or 0),
                        )
                        report.candidates_created_or_updated += 1
                    except Exception as exc:
                        report.rows_skipped += 1
                        report.errors.append(f"candidates!{row_no}: {type(exc).__name__}: {exc}")

        if "keywords" in workbook.sheet_names:
            rows = workbook.get_sheet_by_name("keywords").to_python()
            if rows:
                headers = [str(v).strip() if v is not None else "" for v in rows[0]]
                index = {name: i for i, name in enumerate(headers) if name}
                for row_no, row in enumerate(rows[1:], start=2):
                    keyword = _text(_value(row, index, "keyword"))
                    if not keyword:
                        continue
                    try:
                        add_keyword(
                            session,
                            keyword,
                            kind=_text(_value(row, index, "kind")) or "positive",
                            priority=_int(_value(row, index, "priority"), 50),
                            merchant=_text(_value(row, index, "merchant")),
                            category=_text(_value(row, index, "category")),
                            subcategory=_text(_value(row, index, "subcategory")),
                            enabled=_bool(_value(row, index, "enabled"), True),
                        )
                        report.keywords_created += 1
                    except ValueError as exc:
                        if "already exists" in str(exc):
                            continue
                        report.rows_skipped += 1
                        report.errors.append(f"keywords!{row_no}: ValueError: {exc}")
        session.commit()
    return report
