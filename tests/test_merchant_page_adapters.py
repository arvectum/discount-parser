from __future__ import annotations

from src.sources.adapters.promko import PromkoAdapter
from src.sources.adapters.promokood import PromokoodAdapter


def test_promko_merchant_cards_keep_stable_coupon_ids() -> None:
    html = '''<article><h3>Скидка 16%</h3><p>до 31.12.2026</p><a data-coupon-id="15796">Показать промокод</a></article><article><h3>Скидка 10%</h3><a data-coupon-id="15797" data-promocode="VISIBLE10">Показать промокод</a></article>'''
    offers = PromkoAdapter("https://promko.net/ru/shops/aravia").parse(html)
    assert [x.external_id for x in offers] == ["promko-coupon:15796", "promko-coupon:15797"]
    assert offers[0].promo_code is None and offers[0].raw_payload["needs_reveal"] is True
    assert offers[1].promo_code == "VISIBLE10"


def test_promokood_merchant_cards_are_separate() -> None:
    html = '''<article><h3>Промокод на скидку 4%</h3><p>Промокод UXTPCFU8 на любой заказ до 31.05.2026</p><button>Получить промокод</button></article><article><h3>Промокод на скидку 6%</h3><p>Промокод SECOND66 на заказ до 30.06.2026</p><button>Получить промокод</button></article>'''
    offers = PromokoodAdapter("https://promokood.ru/o/vseinstrumenti").parse(html)
    assert len(offers) == 2
    assert {x.promo_code for x in offers} == {"UXTPCFU8", "SECOND66"}
    assert all(x.conditions for x in offers) and all(x.valid_until for x in offers)
