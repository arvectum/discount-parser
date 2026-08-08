from __future__ import annotations

import html
import math
from urllib.parse import urlencode

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select

from src.modules.offers.models import Offer, OfferSourceObservation, ParseRun, Source
from src.shared.db import create_session
from src.web.setup import is_setup_complete

router = APIRouter()

STYLE = '''
<style>
:root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#18212f;background:#f5f7fb}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1240px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.top h1{margin:0;font-size:27px}.muted{color:#64748b}.nav{display:flex;gap:8px;flex-wrap:wrap}.nav a,.btn{display:inline-block;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:650;border:0;cursor:pointer}.nav a{background:#e8edf4;color:#334155}.nav a.active{background:#111827;color:#fff}.card{background:#fff;border:1px solid #e5e7eb;border-radius:15px;padding:18px;margin-top:18px;box-shadow:0 5px 18px rgba(15,23,42,.04)}.filters{display:grid;grid-template-columns:2fr repeat(3,1fr) auto;gap:10px;align-items:end}.field label{display:block;font-size:13px;font-weight:650;margin-bottom:5px}.field input,.field select{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;background:white}.btn{background:#111827;color:white}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;padding:10px 8px;border-bottom:1px solid #edf0f4;vertical-align:top;font-size:14px}.table th{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:#64748b}.pill{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700;background:#eef2f7}.success{background:#dcfce7;color:#166534}.failed{background:#fee2e2;color:#991b1b}.partial{background:#fef3c7;color:#92400e}.running{background:#dbeafe;color:#1d4ed8}.errorbox{white-space:pre-wrap;word-break:break-word;background:#fff1f2;border:1px solid #fecdd3;border-radius:9px;padding:9px;color:#9f1239;max-width:520px}.pagination{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:16px}.pagination a{padding:7px 10px;border-radius:8px;background:#eef2f7;color:#334155;text-decoration:none}.kv{display:grid;grid-template-columns:180px 1fr;gap:8px 16px}.links a{color:#0369a1}@media(max-width:850px){.filters{grid-template-columns:1fr 1fr}.table{display:block;overflow-x:auto}.kv{grid-template-columns:1fr}.wrap{padding:17px}}
</style>
'''


def _layout(title: str, body: str, active: str) -> HTMLResponse:
    nav = f'''<div class="nav">
      <a href="/" class="{'active' if active == 'dashboard' else ''}">Главная</a>
      <a href="/offers" class="{'active' if active == 'offers' else ''}">Предложения</a>
      <a href="/runs" class="{'active' if active == 'runs' else ''}">Журнал</a>
      <a href="/setup">Настройки Telegram</a>
    </div>'''
    page = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>{STYLE}</head><body><div class="wrap"><div class="top"><div><h1>{html.escape(title)}</h1><div class="muted">Discount Parser</div></div>{nav}</div>{body}</div></body></html>'''
    return HTMLResponse(page)


def _require_setup():
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    return None


@router.get('/offers', response_class=HTMLResponse)
def offers_page(
    q: str = Query('', max_length=200),
    status: str = Query(''),
    category: str = Query(''),
    offer_type: str = Query(''),
    page: int = Query(1, ge=1),
):
    redirect = _require_setup()
    if redirect:
        return redirect

    page_size = 40
    q = q.strip()
    status = status.strip()
    category = category.strip()
    offer_type = offer_type.strip()

    with create_session() as session:
        query = select(Offer)
        count_query = select(func.count()).select_from(Offer)
        conditions = []
        if q:
            token = f'%{q}%'
            conditions.append(or_(Offer.title.ilike(token), Offer.display_title.ilike(token), Offer.merchant.ilike(token), Offer.promo_code.ilike(token)))
        if status:
            conditions.append(Offer.status == status)
        if category:
            conditions.append(Offer.category == category)
        if offer_type:
            conditions.append(Offer.offer_type == offer_type)
        if conditions:
            query = query.where(*conditions)
            count_query = count_query.where(*conditions)

        total = int(session.scalar(count_query) or 0)
        offers = list(session.scalars(query.order_by(Offer.last_seen_at.desc()).offset((page - 1) * page_size).limit(page_size)).all())
        categories = [value for value in session.scalars(select(Offer.category).where(Offer.category.is_not(None), Offer.category != '').distinct().order_by(Offer.category)).all() if value]

    status_options = ['new', 'ready', 'needs_review', 'published', 'expired', 'rejected']
    type_options = ['discount', 'promo', 'cashback', 'delivery', 'other']

    def options(values, current, label):
        rows = [f'<option value="">{html.escape(label)}</option>']
        for value in values:
            selected = ' selected' if value == current else ''
            rows.append(f'<option value="{html.escape(str(value))}"{selected}>{html.escape(str(value))}</option>')
        return ''.join(rows)

    filters = f'''<div class="card"><form method="get" class="filters">
      <div class="field"><label>Поиск</label><input name="q" value="{html.escape(q)}" placeholder="Название, магазин, промокод"></div>
      <div class="field"><label>Статус</label><select name="status">{options(status_options,status,'Все')}</select></div>
      <div class="field"><label>Категория</label><select name="category">{options(categories,category,'Все')}</select></div>
      <div class="field"><label>Тип</label><select name="offer_type">{options(type_options,offer_type,'Все')}</select></div>
      <button class="btn" type="submit">Найти</button>
    </form></div>'''

    rows = []
    for offer in offers:
        benefit = f'{offer.discount_percent:g}%' if offer.discount_percent is not None else (offer.promo_code or '—')
        rows.append(f'''<tr>
          <td><a href="/offers/{offer.id}">#{offer.id}</a></td>
          <td><b>{html.escape(offer.display_title or offer.title)}</b><div class="muted">{html.escape(offer.merchant or '—')}</div></td>
          <td><span class="pill">{html.escape(offer.status)}</span></td>
          <td>{html.escape(offer.category or '—')}<div class="muted">{html.escape(offer.subcategory or '')}</div></td>
          <td>{html.escape(offer.offer_type)}</td><td>{html.escape(str(benefit))}</td>
          <td>{html.escape(str(offer.last_seen_at)[:19])}</td>
        </tr>''')
    table = '<p class="muted">Ничего не найдено.</p>' if not rows else f'''<table class="table"><thead><tr><th>ID</th><th>Предложение</th><th>Статус</th><th>Категория</th><th>Тип</th><th>Выгода</th><th>Последний раз</th></tr></thead><tbody>{''.join(rows)}</tbody></table>'''

    pages = max(1, math.ceil(total / page_size))
    base = {'q': q, 'status': status, 'category': category, 'offer_type': offer_type}
    pagination = '<div class="pagination">'
    if page > 1:
        pagination += f'<a href="/offers?{urlencode({**base, "page": page-1})}">← Назад</a>'
    pagination += f'<span class="muted">Страница {page} из {pages} · всего {total}</span>'
    if page < pages:
        pagination += f'<a href="/offers?{urlencode({**base, "page": page+1})}">Далее →</a>'
    pagination += '</div>'
    return _layout('Предложения', filters + f'<div class="card">{table}{pagination}</div>', 'offers')


@router.get('/offers/{offer_id}', response_class=HTMLResponse)
def offer_detail(offer_id: int):
    redirect = _require_setup()
    if redirect:
        return redirect
    with create_session() as session:
        offer = session.get(Offer, offer_id)
        if offer is None:
            return _layout('Предложение не найдено', '<div class="card">Такого Offer нет.</div>', 'offers')
        observations = session.execute(
            select(OfferSourceObservation, Source).join(Source, Source.id == OfferSourceObservation.source_id).where(OfferSourceObservation.offer_id == offer_id).order_by(OfferSourceObservation.observed_at.desc())
        ).all()

    link = f'<a href="{html.escape(offer.canonical_url)}" target="_blank" rel="noopener">Открыть исходную страницу</a>' if offer.canonical_url else '—'
    kv = [
        ('Статус', offer.status), ('Тип', offer.offer_type), ('Название', offer.display_title or offer.title), ('Магазин', offer.merchant or '—'),
        ('Категория', f'{offer.category or "—"} / {offer.subcategory or "—"}'), ('Скидка', str(offer.discount_percent or '—')), ('Промокод', offer.promo_code or '—'),
        ('Первое появление', str(offer.first_seen_at)), ('Последнее появление', str(offer.last_seen_at)), ('Ссылка', link),
    ]
    body = '<div class="card"><div class="kv">' + ''.join(f'<b>{html.escape(k)}</b><div class="links">{v if k == "Ссылка" else html.escape(str(v))}</div>' for k, v in kv) + '</div></div>'
    obs_rows = ''.join(f'<tr><td>{html.escape(src.name)}</td><td>{html.escape(obs.external_id or "—")}</td><td>{html.escape(str(obs.observed_at))}</td><td><a href="{html.escape(obs.source_url)}" target="_blank" rel="noopener">Источник</a></td></tr>' for obs, src in observations)
    body += f'<div class="card"><h3>Источники и наблюдения</h3><table class="table"><thead><tr><th>Источник</th><th>External ID</th><th>Когда</th><th>URL</th></tr></thead><tbody>{obs_rows}</tbody></table></div>'
    return _layout(f'Предложение #{offer_id}', body, 'offers')


@router.get('/runs', response_class=HTMLResponse)
def runs_page(status: str = Query(''), source: str = Query('')):
    redirect = _require_setup()
    if redirect:
        return redirect
    status = status.strip()
    source = source.strip()
    with create_session() as session:
        query = select(ParseRun, Source).outerjoin(Source, Source.id == ParseRun.source_id)
        if status:
            query = query.where(ParseRun.status == status)
        if source:
            query = query.where(Source.key == source)
        rows = session.execute(query.order_by(ParseRun.started_at.desc()).limit(150)).all()
        sources = session.scalars(select(Source).order_by(Source.name)).all()

    def opts(values, current, all_label):
        out = [f'<option value="">{all_label}</option>']
        for value, label in values:
            selected = ' selected' if value == current else ''
            out.append(f'<option value="{html.escape(value)}"{selected}>{html.escape(label)}</option>')
        return ''.join(out)

    filters = f'''<div class="card"><form method="get" class="filters" style="grid-template-columns:1fr 1fr auto">
      <div class="field"><label>Статус</label><select name="status">{opts([(x,x) for x in ('running','success','partial','failed')],status,'Все')}</select></div>
      <div class="field"><label>Источник</label><select name="source">{opts([(x.key,x.name) for x in sources],source,'Все')}</select></div>
      <button class="btn">Применить</button></form></div>'''

    run_rows = []
    for run, src in rows:
        err = f'<div class="errorbox">{html.escape(run.error[:3000])}</div>' if run.error else '—'
        run_rows.append(f'''<tr><td>#{run.id}</td><td>{html.escape(src.name if src else '—')}<div class="muted">{html.escape(src.key if src else '')}</div></td><td><span class="pill {html.escape(run.status)}">{html.escape(run.status)}</span></td><td>{html.escape(str(run.started_at)[:19])}<div class="muted">→ {html.escape(str(run.finished_at)[:19]) if run.finished_at else '...'}</div></td><td>{run.fetched_count}<div class="muted">new {run.new_count} · upd {run.updated_count} · review {run.review_count}</div></td><td>{run.error_count}</td><td>{err}</td></tr>''')
    table = '<p class="muted">Запусков пока нет.</p>' if not run_rows else f'<table class="table"><thead><tr><th>ID</th><th>Источник</th><th>Статус</th><th>Время</th><th>Данные</th><th>Ошибки</th><th>Текст ошибки</th></tr></thead><tbody>{"".join(run_rows)}</tbody></table>'
    return _layout('Журнал запусков', filters + f'<div class="card">{table}</div>', 'runs')
