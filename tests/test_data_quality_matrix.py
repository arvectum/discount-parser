from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.core.conditions import extract_conditions
from src.core.geo import extract_geo
from src.core.validity import extract_valid_until
from src.modules.offers.models import Offer, Publication
from src.modules.publishing.service import PublishCriteria, list_publish_candidates
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime


MATRIX = json.loads(Path('tests/fixtures/data_quality_matrix.json').read_text(encoding='utf-8'))


def test_data_quality_matrix_schema() -> None:
    assert MATRIX['schema_version'] == 1
    assert set(MATRIX) == {'schema_version', 'validity', 'conditions', 'geo', 'publication'}


def test_validity_matrix() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    for case in MATRIX['validity']:
        value = extract_valid_until(case['text'], now=now)
        actual = value.date().isoformat() if value else None
        assert actual == case['expected'], case


def test_conditions_matrix() -> None:
    for case in MATRIX['conditions']:
        result = extract_conditions(case['text'])
        assert (str(result.max_discount_amount) if result.max_discount_amount is not None else None) == case['max_discount_amount']
        assert (str(result.min_order_amount) if result.min_order_amount is not None else None) == case['min_order_amount']
        for token in case['conditions_contains']:
            assert result.conditions and token in result.conditions
        if not case['conditions_contains']:
            assert result.conditions is None


def test_geo_matrix() -> None:
    for case in MATRIX['geo']:
        result = extract_geo(case['text'])
        assert result.scope == case['scope'], case
        assert result.city == case['city'], case
        assert result.region == case['region'], case


@pytest.fixture
def publication_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / 'quality-matrix.db'
    monkeypatch.setenv('DP_DATABASE_URL', f'sqlite:///{db_path}')
    get_settings.cache_clear()
    reset_db_runtime()
    Base.metadata.create_all(get_engine())
    try:
        yield db_path
    finally:
        reset_db_runtime()
        get_settings.cache_clear()


def test_publication_readiness_matrix(publication_db: Path) -> None:
    channel = '@quality-matrix'
    created: list[tuple[int, dict]] = []
    with create_session() as session:
        for index, case in enumerate(MATRIX['publication']):
            offer = Offer(
                title=f'matrix-{index}',
                status=case['status'],
                discount_percent=Decimal(case['discount_percent']),
            )
            session.add(offer)
            session.flush()
            if case['published_state']:
                session.add(Publication(offer_id=offer.id, channel_id=channel, status=case['published_state']))
            created.append((offer.id, case))
        session.commit()

    with create_session() as session:
        result = list_publish_candidates(
            session,
            channel_id=channel,
            criteria=PublishCriteria(min_discount_percent=Decimal('20'), limit=100),
        )
        eligible_ids = {offer.id for offer in result}

    for offer_id, case in created:
        assert (offer_id in eligible_ids) is case['eligible'], case
