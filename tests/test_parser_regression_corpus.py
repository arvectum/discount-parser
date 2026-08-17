from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from src.sources.adapters.berikod import BerikodAdapter
from src.sources.adapters.promko import PromkoAdapter
from src.sources.adapters.promokodi_net_ru import PromokodiNetRuAdapter
from src.sources.adapters.promokodik import PromokodikAdapter
from src.sources.adapters.promokood import PromokoodAdapter


FIXTURES = Path('tests/fixtures')
ADAPTERS = {
    'berikod': BerikodAdapter,
    'promko': PromkoAdapter,
    'promokodi_net_ru': PromokodiNetRuAdapter,
    'promokodik': PromokodikAdapter,
    'promokood': PromokoodAdapter,
}


def _decimal_text(value):
    if value is None:
        return None
    return str(Decimal(value).normalize())


def _matches(offer, expected: dict) -> bool:
    for field, value in expected.items():
        if field == 'title_contains':
            if value not in offer.title:
                return False
        elif field in {'discount_percent', 'discount_amount', 'cashback_percent'}:
            if _decimal_text(getattr(offer, field)) != _decimal_text(value):
                return False
        elif getattr(offer, field) != value:
            return False
    return True


def test_versioned_parser_corpus_covers_all_html_adapters() -> None:
    manifest = json.loads((FIXTURES / 'parser_corpus.json').read_text(encoding='utf-8'))
    assert manifest['schema_version'] == 1
    cases = manifest['cases']
    assert {case['adapter'] for case in cases} == set(ADAPTERS)

    for case in cases:
        fixture = FIXTURES / case['fixture']
        assert fixture.is_file(), case['fixture']
        adapter = ADAPTERS[case['adapter']](case['base_url'])
        offers = adapter.parse(fixture.read_text(encoding='utf-8'))
        assert len(offers) == case['expected_count'], case['adapter']
        for expected in case['offers']:
            assert any(_matches(offer, expected) for offer in offers), (case['adapter'], expected, offers)
