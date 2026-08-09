from __future__ import annotations

import html
import math
from pathlib import Path
from urllib.parse import quote

import yaml
from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from src.modules.offers.models import Offer, OfferSourceObservation, Source
from src.modules.offers.repository import OfferRepository
from src.shared.db import create_session, session_scope
from src.telegram.render import render_offer_caption
from src.web.setup import is_setup_complete

router = APIRouter()


def _require_setup():
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    return None


def _categories() -> list[str]:
    path = Path('config/taxonomy.yaml')
    values: list[str] = []
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            values = [str(row.get('name')) for row in data.get('categories', []) if row.get('name')]
        except Exception:
            values = []
    return values or ['Продукты', 'Детские товары', 'Электроника', 'Бытовая техника', 'Одежда', 'Обувь', 'Красота и здоровье', 'Дом и быт', 'Доставка/сервисы', 'Другое']


def _geo_label(offer: Offer) -> str:
    if offer.geo_scope == 'all_russia':
        return 'Вся Россия'
    parts = [x for x in (offer.city, offer.region) if x]
    return ', '.join(dict.fromkeys(parts)) if parts else 'Не определено'


def _benefit(offer: Offer) -> str:
    parts: list[str] = []
    if offer.discount_percent is not None:
        parts.append(f'скидка {offer.discount_percent:g}%')
    if offer.discount_amount is not None:
        parts.append(f'скидка {offer.discount_amount:g} ₽')
    if offer.cashback_percent is not None:
        parts.append(f'кэшбэк {offer.cashback_percent:g}%')
    if offer.cashback_amount is not None:
        parts.append(f'кэшбэк {offer.cashback_amount:g} ₽')
    if offer.promo_code:
        parts.append(f'промокод {offer.promo_code}')
    return ' · '.join(parts) or 'выгода не распознана'


def _option(value: str, current: str | None, label: str | None = None) -> str:
    selected = ' selected' if value == (current or '') else ''
    return f'<option value="{html.escape(value)}"{selected}>{html.escape(label or value)}</option>'


@router.get('/review', response_class=HTMLResponse)
def review_page(
    status: str = Query('needs_review'),
    page: int = Query(1, ge=1),
    message: str | None = None,
):
    redirect = _require_setup()
    if redirect:
        return redirect
    if status not in {'needs_review', 'rejected', 'ready'}:
        status = 'needs_review'
    page_size = 20
    with create_session() as session:
        total = int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == status)) or 0)
        offers = list(session.scalars(select(Offer).where(Offer.status == status).order_by(Offer.last_seen_at.desc()).offset((page - 1) * page_size).limit(page_size)).all())
        ids = [offer.id for offer in offers]
        observations = session.execute(
            select(OfferSourceObservation, Source)
            .join(Source, Source.id == OfferSourceObservation.source_id)
            .where(OfferSourceObservation.offer_id.in_(ids) if ids else False)
            .order_by(OfferSourceObservation.observed_at.desc())
        ).all() if ids else []
    source_by_offer: dict[int, tuple[OfferSourceObservation, Source]] = {}
    for obs, src in observations:
        source_by_offer.setdefault(obs.offer_id, (obs, src))

    categories = _categories()
    cards: list[str] = []
    for offer in offers:
        source = source_by_offer.get(offer.id)
        source_html = 'Источник не сохранён'
        if source:
            obs, src = source
            source_html = f'{html.escape(src.name)} · <a href="{html.escape(obs.source_url)}" target="_blank" rel="noopener">открыть оригинал</a>'
        category_values = list(dict.fromkeys(([offer.category] if offer.category else []) + categories))
        category_options = ''.join(_option(v, offer.category) for v in category_values if v)
        geo_options = ''.join([
            _option('unknown', offer.geo_scope, 'Не определено'),
            _option('all_russia', offer.geo_scope, 'Вся Россия'),
            _option('region', offer.geo_scope, 'Регион'),
            _option('city', offer.geo_scope, 'Город'),
        ])
        publication_preview = render_offer_caption(offer)
        cards.append(f'''<article class="review-card"><div class="review-card-head"><div><h3 style="margin:0 0 4px">#{offer.id} · {html.escape(offer.display_title or offer.title)}</h3><div class="muted">{html.escape(offer.merchant or 'Поставщик не определён')} · {html.escape(_benefit(offer))} · 📍 {html.escape(_geo_label(offer))}</div></div><span class="pill">{html.escape(offer.status)}</span></div><div class="review-source" style="margin-top:8px">{source_html}</div><div class="review-source-block"><div class="review-block-label">Исходный текст</div><div class="review-description">{html.escape((offer.description or 'Описание отсутствует')[:1800])}</div></div><div class="review-preview"><div class="review-block-label">Как будет выглядеть публикация</div><div class="review-preview-body">{publication_preview}</div><div class="muted" style="margin-top:8px">Пост строится из структурированных полей. Полный текст источника в Telegram не копируется.</div></div><form method="post" action="/review/{offer.id}"><div class="review-fields"><div class="field wide"><label>Название для публикации</label><input name="display_title" value="{html.escape(offer.display_title or offer.title)}"></div><div class="field"><label>Категория</label><select name="category">{category_options}</select></div><div class="field"><label>Подкатегория</label><input name="subcategory" value="{html.escape(offer.subcategory or '')}" placeholder="необязательно"></div><div class="field"><label>ГЕО</label><select name="geo_scope">{geo_options}</select></div><div class="field"><label>Регион</label><input name="region" value="{html.escape(offer.region or '')}"></div><div class="field"><label>Город</label><input name="city" value="{html.escape(offer.city or '')}"></div><div class="field wide"><label>Условия</label><textarea name="conditions">{html.escape(offer.conditions or '')}</textarea></div></div><div class="review-actions"><button class="btn secondary" name="action" value="save">Сохранить правки</button><button class="btn good" name="action" value="approve">Одобрить → ready</button><button class="btn bad" name="action" value="reject">Отклонить</button></div></form></article>''')

    tabs = ''.join([
        f'<a class="btn {"good" if status == "needs_review" else "secondary"}" href="/review?status=needs_review">На проверке</a>',
        f'<a class="btn {"good" if status == "ready" else "secondary"}" href="/review?status=ready">Готовые</a>',
        f'<a class="btn {"good" if status == "rejected" else "secondary"}" href="/review?status=rejected">Отклонённые</a>',
    ])
    flash = f'<div class="ok" style="margin:14px 0">{html.escape(message)}</div>' if message else ''
    pages = max(1, math.ceil(total / page_size))
    pagination = f'<div class="row" style="justify-content:flex-end;margin-top:16px"><span class="muted">Страница {page} из {pages} · всего {total}</span>'
    if page > 1:
        pagination += f'<a class="btn secondary" href="/review?status={status}&page={page-1}">← Назад</a>'
    if page < pages:
        pagination += f'<a class="btn secondary" href="/review?status={status}&page={page+1}">Далее →</a>'
    pagination += '</div>'
    body = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Проверка предложений</title><style>.wrap{{max-width:1240px;margin:auto;padding:28px}}.row{{display:flex;gap:9px;flex-wrap:wrap;align-items:center}}.muted{{color:#64748b}}.field label{{display:block;font-size:13px;font-weight:700;margin-bottom:5px}}.field input,.field select{{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff}}.btn{{display:inline-block;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:700;border:0;cursor:pointer}}.pill{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700;background:#eef2f7}}.ok{{background:#dcfce7;color:#166534;padding:12px;border-radius:10px}}.review-source-block{{margin-top:12px}}.review-block-label{{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:#64748b;margin-bottom:6px}}.review-preview{{margin:14px 0;padding:14px;border:1px solid #b7eadf;border-radius:12px;background:#f2fffb}}.review-preview-body{{white-space:pre-line;line-height:1.5;color:#001432}}</style></head><body><main class="wrap"><div class="row" style="justify-content:space-between"><div><h1 style="margin:0">Проверка предложений</h1><div class="muted">Правки сохраняются как manual override и не будут затёрты следующим парсингом.</div></div><div class="row">{tabs}</div></div>{flash}<div class="review-grid" style="margin-top:18px">{''.join(cards) if cards else '<div class="review-card">Предложений в этом статусе нет.</div>'}</div>{pagination}</main></body></html>'''
    return HTMLResponse(body)


@router.post('/review/{offer_id}')
def review_action(
    offer_id: int,
    action: str = Form('save'),
    display_title: str = Form(''),
    category: str = Form(''),
    subcategory: str = Form(''),
    geo_scope: str = Form('unknown'),
    region: str = Form(''),
    city: str = Form(''),
    conditions: str = Form(''),
):
    redirect = _require_setup()
    if redirect:
        return redirect
    if action not in {'save', 'approve', 'reject'}:
        return HTMLResponse('Unsupported action', status_code=400)
    if geo_scope not in {'unknown', 'all_russia', 'region', 'city'}:
        return HTMLResponse('Unsupported geo scope', status_code=400)
    if action == 'approve' and not category.strip():
        return RedirectResponse('/review?message=' + quote('Для одобрения укажите категорию'), status_code=303)
    with session_scope() as session:
        offer = session.get(Offer, offer_id)
        if offer is None:
            return HTMLResponse('Offer not found', status_code=404)
        repo = OfferRepository(session)
        values = {
            'display_title': display_title.strip() or offer.title,
            'category': category.strip() or None,
            'subcategory': subcategory.strip() or None,
            'geo_scope': geo_scope,
            'region': region.strip() or None,
            'city': city.strip() or None,
            'conditions': conditions.strip() or None,
        }
        for field_name, value in values.items():
            repo.set_manual_override(offer, field_name, value, source='web_review')
        if action == 'approve':
            repo.set_manual_override(offer, 'status', 'ready', source='web_review')
            message = 'Предложение одобрено и переведено в ready'
        elif action == 'reject':
            repo.set_manual_override(offer, 'status', 'rejected', source='web_review')
            message = 'Предложение отклонено'
        else:
            message = 'Правки сохранены'
    return RedirectResponse('/review?message=' + quote(message), status_code=303)
