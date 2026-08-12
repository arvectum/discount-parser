from __future__ import annotations

import html
import json
from urllib.parse import quote

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from src.telegram.publication_format import (
    FIELD_DEFINITIONS,
    load_publication_format,
    reset_publication_format,
    save_publication_format,
)
from src.web.setup import is_setup_complete


router = APIRouter()

_FIELD_SAMPLE = {
    "merchant": "🏪 Поставщик: Лента",
    "price": "💰 Цена: 4 000 ₽ → 3 000 ₽",
    "discount": "💸 Скидка: 25%",
    "cashback": "💳 Кэшбэк: 10%",
    "delivery": "🚚 Доставка: 0 ₽",
    "category": "📂 Категория: Продукты",
    "conditions": "📌 Условия: заказ от 3 000 ₽; максимум 700 ₽",
    "geo": "📍 ГЕО: Вся Россия",
    "valid_until": "⏳ До: 18.08.2026",
    "promo_code": "🎁 Промокод: SUMMER25",
}

_STYLE = '''<style>
.tf-wrap{max-width:1080px;margin:auto;padding:28px}.tf-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-end;margin-bottom:18px}.tf-head h1{margin:0 0 5px;font-size:30px}.tf-lead{color:#64748b;max-width:720px}.tf-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(320px,.9fr);gap:18px}.tf-card{background:#fff;border:1px solid #dce5e9;border-radius:16px;padding:20px}.tf-row{display:grid;grid-template-columns:34px 28px minmax(0,1fr) 38px 38px;align-items:center;gap:8px;padding:10px 8px;border:1px solid #e3eaed;border-radius:10px;margin:7px 0;background:#fff}.tf-row.dragging{opacity:.55}.tf-handle{cursor:grab;color:#80909c;font-size:19px;text-align:center}.tf-row input{width:18px;height:18px}.tf-label{font-weight:750}.tf-move{border:1px solid #d4dfe4;background:#fff;border-radius:8px;width:36px;height:34px;cursor:pointer}.tf-preview{background:#f6faf9;border:1px solid #dce9e5;border-radius:13px;padding:17px;white-space:pre-line;line-height:1.55;min-height:240px}.tf-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}.tf-primary,.tf-secondary{display:inline-block;border-radius:9px;padding:10px 14px;font-weight:800;cursor:pointer;text-decoration:none}.tf-primary{border:0;background:#00C8A0;color:#001432}.tf-secondary{border:1px solid #C8D2DC;background:#fff;color:#001432}.tf-note{background:#ecfffa;border:1px solid #b3f4e5;border-radius:11px;padding:11px 13px;margin-bottom:14px}.tf-muted{font-size:13px;color:#71808f}.tf-badge{display:inline-block;background:#eef4f4;border-radius:999px;padding:4px 8px;font-size:12px;font-weight:750}@media(max-width:800px){.tf-wrap{padding:18px}.tf-grid{grid-template-columns:1fr}.tf-head{align-items:flex-start;flex-direction:column}.tf-row{grid-template-columns:30px 26px minmax(0,1fr) 36px 36px}}
</style>'''


def _require_setup():
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    return None


@router.get('/settings/telegram-format', response_class=HTMLResponse)
def telegram_format_page(message: str | None = None):
    redirect = _require_setup()
    if redirect:
        return redirect
    current = load_publication_format()
    labels = dict(FIELD_DEFINITIONS)
    rows: list[str] = []
    for key in current.order:
        checked = ' checked' if key in current.enabled else ''
        rows.append(
            f'''<div class="tf-row" draggable="true" data-field="{html.escape(key)}"><span class="tf-handle" title="Перетащить">⋮⋮</span><input type="checkbox" name="enabled" value="{html.escape(key)}"{checked} aria-label="Показывать {html.escape(labels[key])}"><span class="tf-label">{html.escape(labels[key])}</span><button class="tf-move" type="button" data-move="up" aria-label="Поднять">↑</button><button class="tf-move" type="button" data-move="down" aria-label="Опустить">↓</button></div>'''
        )
    flash = f'<div class="tf-note">{html.escape(message)}</div>' if message else ''
    sample_json = json.dumps(_FIELD_SAMPLE, ensure_ascii=False).replace('</', '<\\/')
    body = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Формат публикации Telegram</title>{_STYLE}</head><body><main class="tf-wrap"><section class="tf-head"><div><h1>Формат публикации Telegram</h1><div class="tf-lead">Выберите, какие поля показывать в посте, и расположите их в нужном порядке. Заголовок и кнопка перехода остаются всегда.</div></div><a class="tf-secondary" href="/settings">← Настройки</a></section>{flash}<div class="tf-grid"><section class="tf-card"><div style="display:flex;justify-content:space-between;gap:12px;align-items:center"><div><h2 style="margin:0 0 4px">Поля поста</h2><div class="tf-muted">Галочка включает поле. Меняйте порядок стрелками или перетаскиванием.</div></div><span class="tf-badge">без кода</span></div><form id="format-form" method="post" action="/settings/telegram-format"><input id="field-order" type="hidden" name="field_order" value="{html.escape(','.join(current.order))}"><div id="field-list">{''.join(rows)}</div><div class="tf-actions"><button class="tf-primary" type="submit">Сохранить формат</button><button class="tf-secondary" type="submit" formaction="/settings/telegram-format/reset">Вернуть стандартный</button></div></form></section><aside class="tf-card"><h2 style="margin-top:0">Предпросмотр</h2><div class="tf-muted" style="margin-bottom:10px">Пример меняется сразу. Реальный пост использует данные конкретного предложения.</div><div id="tf-preview" class="tf-preview"></div><div class="tf-muted" style="margin-top:10px">Полный исходный текст объявления в Telegram не копируется.</div></aside></div></main><script>
const samples = {sample_json};
const list = document.getElementById('field-list');
const orderInput = document.getElementById('field-order');
const preview = document.getElementById('tf-preview');
function rows(){{return [...list.querySelectorAll('.tf-row')]}}
function sync(){{
  orderInput.value = rows().map(r => r.dataset.field).join(',');
  const lines = ['🔥 Скидка на продукты', ''];
  rows().forEach(r => {{ const cb=r.querySelector('input[type=checkbox]'); if(cb.checked) lines.push(samples[r.dataset.field]); }});
  preview.textContent = lines.join('\n');
}}
list.addEventListener('change', sync);
list.addEventListener('click', e => {{
  const b=e.target.closest('[data-move]'); if(!b) return;
  const row=b.closest('.tf-row');
  if(b.dataset.move==='up' && row.previousElementSibling) list.insertBefore(row,row.previousElementSibling);
  if(b.dataset.move==='down' && row.nextElementSibling) list.insertBefore(row.nextElementSibling,row);
  sync();
}});
let dragged=null;
list.addEventListener('dragstart', e => {{ dragged=e.target.closest('.tf-row'); if(dragged) dragged.classList.add('dragging'); }});
list.addEventListener('dragend', () => {{ if(dragged) dragged.classList.remove('dragging'); dragged=null; sync(); }});
list.addEventListener('dragover', e => {{
  e.preventDefault(); if(!dragged) return;
  const target=e.target.closest('.tf-row'); if(!target || target===dragged) return;
  const box=target.getBoundingClientRect();
  list.insertBefore(dragged, e.clientY < box.top + box.height/2 ? target : target.nextSibling);
}});
sync();
</script></body></html>'''
    return HTMLResponse(body)


@router.post('/settings/telegram-format')
def save_telegram_format(field_order: str = Form(''), enabled: list[str] = Form([])):
    redirect = _require_setup()
    if redirect:
        return redirect
    order = [value.strip() for value in field_order.split(',') if value.strip()]
    save_publication_format(order=order, enabled=enabled)
    return RedirectResponse('/settings/telegram-format?message=' + quote('Формат публикации сохранён'), status_code=303)


@router.post('/settings/telegram-format/reset')
def reset_telegram_format_route():
    redirect = _require_setup()
    if redirect:
        return redirect
    reset_publication_format()
    return RedirectResponse('/settings/telegram-format?message=' + quote('Стандартный формат восстановлен'), status_code=303)
