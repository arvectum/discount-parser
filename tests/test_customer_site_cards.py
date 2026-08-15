from __future__ import annotations

from src.sources.adapters.promko import PromkoAdapter


def test_promko_masked_value_is_not_a_promo_code() -> None:
    html = '<article><h3>Скидка 20%</h3><button data-coupon-id="10" data-promocode="••••••">Показать промокод</button></article>'
    offer = PromkoAdapter("https://promko.net/ru/shops/aravia").parse(html)[0]
    assert offer.promo_code is None
    assert offer.raw_payload["promko_coupon_id"] == "10"
