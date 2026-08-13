from __future__ import annotations

import html
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.background import BackgroundTask
from sqlalchemy import select

from src.modules.source_registry.collectors import COLLECTORS
from src.modules.source_registry.models import PLATFORMS, TRUST_LEVELS, RegisteredSource, SourceCandidate, SourceKeyword
from src.modules.source_registry.runner import collect_registered_source
from src.modules.source_registry.service import add_keyword, create_source, review_candidate, set_source_enabled
from src.modules.source_registry.xlsx import export_source_registry_xlsx, import_source_registry_xlsx
from src.shared.db import create_session, session_scope
from src.web.setup import is_setup_complete

router = APIRouter()

STYLE = '''<style>
:root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#18212f;background:#f5f7fb}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1280px;margin:auto;padding:28px}.nav,.row{display:flex;gap:9px;flex-wrap:wrap;align-items:center}.nav a,.btn{display:inline-block;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:650;border:0;cursor:pointer}.nav a{background:#e8edf4;color:#334155}.btn{background:#111827;color:#fff}.btn.secondary{background:#e5e7eb;color:#111827}.btn.good{background:#0f766e}.btn.bad{background:#b91c1c}.card{background:#fff;border:1px solid #e5e7eb;border-radius:15px;padding:18px;margin-top:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.field label{display:block;font-size:13px;font-weight:650;margin-bottom:5px}.field input,.field select{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff}.table{width:100%;border-collapse:collapse;font-size:13px}.table th,.table td{text-align:left;padding:9px;border-bottom:1px solid #e5e7eb;vertical-align:top}.table th{color:#475569}.pill{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:700;background:#e2e8f0}.on{background:#dcfce7;color:#166534}.off{background:#fee2e2;color:#991b1b}.warn{background:#fef3c7;color:#92400e}.muted{color:#64748b}.flash{padding:12px;border-radius:10px;background:#dcfce7;color:#166534;margin-top:16px}.err{padding:12px;border-radius:10px;background:#fee2e2;color:#991b1b;margin-top:16px}h1,h2,h3{margin-top:0}.scroll{overflow:auto}
</style>'''


def _layout(title: str, body: str) -> HTMLResponse:
    nav = '''<div class="nav"><a href="/">Главная</a><a href="/sources-registry">Источники</a><a href="/offers">Предложения</a><a href="/runs">Журнал</a><a href="/system">Система</a></div>'''
    return HTMLResponse(
        f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>{STYLE}</head><body><div class="wrap"><div class="row" style="justify-content:space-between"><div><h1>{html.escape(title)}</h1><div class="muted">Единая база сайтов, каналов и сообществ</div></div>{nav}</div>{body}</div></body></html>'
    )


def _require_setup():
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    return None


def _option(value: str, label: str | None = None) -> str:
    return f'<option value="{html.escape(value)}">{html.escape(label or value)}</option>'


def _selected_options(values: tuple[str, ...], selected: str) -> str:
    return ''.join(
        f'<option value="{html.escape(value)}{" selected" if value == selected else ""}>{html.escape(value)}</option>'
        for value in values
    )


def _source_form_fields(source: RegisteredSource) -> str:
    fields = (
        ('item_selector', 'Контейнер предложения'), ('title_selector', 'Название'),
        ('promo_code_selector', 'Промокод'), ('promo_code_attribute', 'Атрибут промокода'),
        ('conditions_selector', 'Условия'), ('valid_until_selector', 'Срок действия'),
        ('link_selector', 'Ссылка'), ('reveal_selector', 'Элемент раскрытия'),
        ('reveal_code_attribute', 'Атрибут раскрытия'),
    )
    return ''.join(
        f'<div class="field"><label>{label}</label><input name="{name}" value="{html.escape(str(getattr(source, name) or ""))}"></div>'
        for name, label in fields
    )


@router.get('/sources-registry', response_class=HTMLResponse)
def registry_page(message: str | None = None, error: str | None = None):
    redirect = _require_setup()
    if redirect:
        return redirect
    with create_session() as session:
        sources = session.scalars(select(RegisteredSource).order_by(RegisteredSource.platform, RegisteredSource.priority.desc(), RegisteredSource.name)).all()
        candidates = session.scalars(select(SourceCandidate).where(SourceCandidate.status == 'new').order_by(SourceCandidate.confidence.desc(), SourceCandidate.id)).all()
        keywords = session.scalars(select(SourceKeyword).order_by(SourceKeyword.enabled.desc(), SourceKeyword.priority.desc(), SourceKeyword.kind, SourceKeyword.keyword)).all()

    source_rows = []
    for source in sources:
        enabled = '<span class="pill on">ВКЛ</span>' if source.enabled else '<span class="pill off">ВЫКЛ</span>'
        status_cls = 'on' if source.status == 'healthy' else ('off' if source.status in {'blocked','degraded'} else 'warn')
        action = 'disable' if source.enabled else 'enable'
        action_label = 'Выключить' if source.enabled else 'Включить'
        delete_action = '' if source.collector_type == 'legacy_adapter' else f'<form method="post" action="/sources-registry/{source.id}/delete"><button class="btn bad">Удалить</button></form>'
        edit_action = f'<a class="btn secondary" href="/sources-registry/{source.id}/edit">Настроить поля</a>'
        source_rows.append(f'''<tr><td><b>{html.escape(source.name)}</b><br><span class="muted">{html.escape(source.key)}</span></td><td>{html.escape(source.platform)}<br><span class="muted">{html.escape(source.source_type)}</span></td><td>{html.escape(source.merchant or '—')}</td><td><a target="_blank" rel="noopener" href="{html.escape(source.url)}">открыть</a><br><span class="muted">{html.escape(source.collector_type)}</span></td><td>{enabled}<br><span class="pill {status_cls}">{html.escape(source.status)}</span></td><td>{html.escape(str(source.last_success_at or '—'))}<br><span class="muted">{html.escape((source.last_error or '')[:160])}</span></td><td><div class="row">{edit_action}<form method="post" action="/sources-registry/{source.id}/{action}"><button class="btn secondary">{action_label}</button></form>{'' if source.collector_type == 'legacy_adapter' else f'<form method="post" action="/sources-registry/{source.id}/test"><button class="btn good">Проверить</button></form>'}{delete_action}</div></td></tr>''')

    candidate_rows = []
    for item in candidates:
        candidate_rows.append(f'''<tr><td>{html.escape(item.name or '—')}</td><td>{html.escape(item.platform)}</td><td>{html.escape(item.merchant or '—')}</td><td><a target="_blank" rel="noopener" href="{html.escape(item.url)}">{html.escape(item.url[:70])}</a></td><td>{item.confidence:.2f}</td><td><div class="row"><form method="post" action="/sources-registry/candidates/{item.id}/approve"><button class="btn good">Одобрить</button></form><form method="post" action="/sources-registry/candidates/{item.id}/reject"><button class="btn bad">Отклонить</button></form></div></td></tr>''')

    keyword_rows = []
    for item in keywords[:200]:
        keyword_rows.append(f'''<tr><td>{html.escape(item.keyword)}</td><td>{html.escape(item.kind)}</td><td>{item.priority}</td><td>{html.escape(item.merchant or 'глобально')}</td><td>{'<span class="pill on">ВКЛ</span>' if item.enabled else '<span class="pill off">ВЫКЛ</span>'}</td><td><form method="post" action="/sources-registry/keywords/{item.id}/toggle"><button class="btn secondary">Переключить</button></form></td></tr>''')

    flash = f'<div class="flash">{html.escape(message)}</div>' if message else ''
    err = f'<div class="err">{html.escape(error)}</div>' if error else ''
    platform_options = ''.join(_option(value) for value in PLATFORMS if value != 'promo_aggregator')
    collector_options = ''.join(_option(value) for value in COLLECTORS)
    trust_options = ''.join(_option(value) for value in TRUST_LEVELS)
    body = f'''{flash}{err}
    <div class="card"><div class="row" style="justify-content:space-between"><div><h2>База источников</h2><div class="muted">Старые promo adapters отображаются вместе с новыми платформами, но продолжают работать через проверенный legacy pipeline.</div></div><div class="row"><a class="btn secondary" href="/sources-registry/export">Скачать XLSX</a><form method="post" action="/sources-registry/import" enctype="multipart/form-data"><input type="file" name="file" accept=".xlsx" required><button class="btn secondary">Импорт</button></form></div></div><div class="scroll"><table class="table"><thead><tr><th>Источник</th><th>Платформа</th><th>Магазин</th><th>URL / collector</th><th>Состояние</th><th>Последний результат</th><th>Действия</th></tr></thead><tbody>{''.join(source_rows) or '<tr><td colspan="7">Реестр пока пуст. Выполните registry-seed или добавьте источник.</td></tr>'}</tbody></table></div></div>

    <div class="card"><h2>Добавить источник</h2><form method="post" action="/sources-registry/add"><div class="grid"><div class="field"><label>Название</label><input name="name" required></div><div class="field"><label>Платформа</label><select name="platform">{platform_options}</select></div><div class="field"><label>Тип</label><input name="source_type" value="social_channel"></div><div class="field"><label>URL</label><input name="url" type="url" required></div><div class="field"><label>External ID / username</label><input name="external_id"></div><div class="field"><label>Магазин</label><input name="merchant"></div><div class="field"><label>Collector</label><select name="collector_type">{collector_options}</select></div><div class="field"><label>Trust</label><select name="trust_level">{trust_options}</select></div><div class="field"><label>Priority 0–100</label><input name="priority" type="number" min="0" max="100" value="50"></div><div class="field"><label>Интервал, минут</label><input name="check_interval_minutes" type="number" min="1" max="10080" value="120"></div></div><h3 style="margin-top:18px">Точная настройка полей сайта</h3><div class="grid">{''.join(f'<div class="field"><label>{label}</label><input name="{name}"></div>' for name,label in [('item_selector','Контейнер предложения'),('title_selector','Название'),('promo_code_selector','Промокод'),('promo_code_attribute','Атрибут промокода'),('conditions_selector','Условия'),('valid_until_selector','Срок действия'),('link_selector','Ссылка'),('reveal_selector','Элемент раскрытия'),('reveal_code_attribute','Атрибут раскрытия')])}</div><button class="btn good" style="margin-top:12px">Добавить</button></form></div>

    <div class="card"><h2>Кандидаты на источники</h2><div class="scroll"><table class="table"><thead><tr><th>Название</th><th>Платформа</th><th>Магазин</th><th>URL</th><th>Confidence</th><th>Review</th></tr></thead><tbody>{''.join(candidate_rows) or '<tr><td colspan="6">Новых кандидатов нет.</td></tr>'}</tbody></table></div></div>

    <div class="card"><h2>Ключевые слова</h2><form method="post" action="/sources-registry/keywords/add"><div class="row"><input name="keyword" placeholder="скидка / название магазина" required style="padding:9px;min-width:250px"><select name="kind" style="padding:9px"><option>strong_positive</option><option selected>positive</option><option>negative</option><option>merchant</option><option>custom</option></select><input name="merchant" placeholder="магазин (необязательно)" style="padding:9px"><input name="priority" type="number" value="50" min="0" max="100" style="padding:9px;width:100px"><button class="btn good">Добавить</button></div></form><div class="scroll" style="margin-top:12px"><table class="table"><thead><tr><th>Keyword</th><th>Kind</th><th>Priority</th><th>Scope</th><th>Enabled</th><th></th></tr></thead><tbody>{''.join(keyword_rows)}</tbody></table></div></div>'''
    return _layout('Источники', body)


@router.post('/sources-registry/add')
def add_source_route(
    name: str = Form(...), platform: str = Form(...), source_type: str = Form('other'), url: str = Form(...),
    external_id: str = Form(''), merchant: str = Form(''), collector_type: str = Form(...),
    trust_level: str = Form('unknown'), priority: int = Form(50), check_interval_minutes: int = Form(120),
    item_selector: str = Form(''), title_selector: str = Form(''), promo_code_selector: str = Form(''), promo_code_attribute: str = Form(''), conditions_selector: str = Form(''), valid_until_selector: str = Form(''), link_selector: str = Form(''), reveal_selector: str = Form(''), reveal_code_attribute: str = Form(''),
):
    try:
        with session_scope() as session:
            create_source(session, name=name, platform=platform, source_type=source_type, url=url,
                          external_id=external_id or None, merchant=merchant or None, collector_type=collector_type,
                          trust_level=trust_level, priority=priority, check_interval_minutes=check_interval_minutes,
                          item_selector=item_selector or None, title_selector=title_selector or None, promo_code_selector=promo_code_selector or None, promo_code_attribute=promo_code_attribute or None, conditions_selector=conditions_selector or None, valid_until_selector=valid_until_selector or None, link_selector=link_selector or None, reveal_selector=reveal_selector or None, reveal_code_attribute=reveal_code_attribute or None)
    except Exception as exc:
        return RedirectResponse('/sources-registry?error=' + quote(f'{type(exc).__name__}: {exc}'), status_code=303)
    return RedirectResponse('/sources-registry?message=' + quote('Источник добавлен'), status_code=303)


def _selected(value: str, current: str) -> str:
    return ' selected' if value == current else ''


def _source_edit_form(source: RegisteredSource) -> str:
    platform_options = ''.join(
        f'<option value="{html.escape(value)}"{_selected(value, source.platform)}>{html.escape(value)}</option>'
        for value in PLATFORMS
    )
    collector_values = list(COLLECTORS)
    if source.collector_type not in collector_values:
        collector_values.insert(0, source.collector_type)
    collector_options = ''.join(
        f'<option value="{html.escape(value)}"{_selected(value, source.collector_type)}>{html.escape(value)}</option>'
        for value in collector_values
    )
    trust_options = ''.join(
        f'<option value="{html.escape(value)}"{_selected(value, source.trust_level)}>{html.escape(value)}</option>'
        for value in TRUST_LEVELS
    )

    def val_func(name: str) -> str:
        return html.escape(str(getattr(source, name) or ''), quote=True)

    selector_fields = [
        ('item_selector', 'Контейнер предложения', '.coupon-card'),
        ('title_selector', 'Название', '.coupon-title'),
        ('promo_code_selector', 'Промокод', '[data-c-text]'),
        ('promo_code_attribute', 'Атрибут промокода', 'data-code'),
        ('conditions_selector', 'Условия', '.conditions'),
        ('valid_until_selector', 'Срок действия', 'time, .valid-until'),
        ('link_selector', 'Ссылка', 'a.offer-link'),
        ('reveal_selector', 'Элемент раскрытия', '[data-coupon-id]'),
        ('reveal_code_attribute', 'Атрибут раскрытия', 'data-coupon-id'),
    ]
    mapping = ''.join(
        f'<div class="field"><label>{html.escape(label)}</label>'
        f'<input name="{name}" value="{val_func(name)}" placeholder="{html.escape(placeholder, quote=True)}"></div>'
        for name, label, placeholder in selector_fields
    )
    return f'''
    <div class="card">
      <h2>Источник: {html.escape(source.name)}</h2>
      <div class="muted">Настройте источник и соответствие элементов страницы полям предложения. Для сайтов используется CSS-селектор: например <code>.coupon-card</code> или <code>[data-c-text]</code>. Пустое поле отключает соответствующее правило. Если это старый legacy-источник, сохранение хотя бы одного селектора автоматически переключит его на точный <code>generic_web</code> маппинг вместо старого адаптера.</div>
      <form method="post" action="/sources-registry/{source.id}/edit" style="margin-top:16px">
        <div class="grid">
          <div class="field"><label>Название источника</label><input name="name" value="{val_func('name')}" required></div>
          <div class="field"><label>Платформа</label><select name="platform">{platform_options}</select></div>
          <div class="field"><label>Тип</label><input name="source_type" value="{val_func('source_type')}"></div>
          <div class="field"><label>URL</label><input name="url" type="url" value="{val_func('url')}" required></div>
          <div class="field"><label>External ID / username</label><input name="external_id" value="{val_func('external_id')}"></div>
          <div class="field"><label>Магазин</label><input name="merchant" value="{val_func('merchant')}"></div>
          <div class="field"><label>Collector</label><select name="collector_type">{collector_options}</select></div>
          <div class="field"><label>Trust</label><select name="trust_level">{trust_options}</select></div>
          <div class="field"><label>Priority 0–100</label><input name="priority" type="number" min="0" max="100" value="{source.priority}"></div>
          <div class="field"><label>Интервал, минут</label><input name="check_interval_minutes" type="number" min="1" max="10080" value="{source.check_interval_minutes}"></div>
        </div>
        <h3 style="margin-top:18px">Маппинг полей сайта</h3>
        <div class="muted" style="margin-bottom:10px">Сначала задайте контейнер одного предложения, затем селекторы внутри него. «Атрибут промокода» нужен, если код хранится не в тексте элемента, а в HTML-атрибуте.</div>
        <div class="grid">{mapping}</div>
        <div class="row" style="margin-top:16px">
          <button class="btn good">Сохранить настройки</button>
          <a class="btn secondary" href="/sources-registry">Отмена</a>
        </div>
      </form>
    </div>'''


@router.get('/sources-registry/{source_id}/edit', response_class=HTMLResponse)
def source_edit_page(source_id: int, error: str | None = None):
    redirect = _require_setup()
    if redirect:
        return redirect
    with create_session() as session:
        source = session.get(RegisteredSource, source_id)
        if source is None:
            return HTMLResponse('Source not found', status_code=404)
        session.expunge(source)
    err = f'<div class="err">{html.escape(error)}</div>' if error else ''
    return _layout('Настройка источника', err + _source_edit_form(source))


@router.post('/sources-registry/{source_id}/edit')
def source_edit_save(
    source_id: int,
    name: str = Form(...), platform: str = Form(...), source_type: str = Form('other'), url: str = Form(...),
    external_id: str = Form(''), merchant: str = Form(''), collector_type: str = Form(...),
    trust_level: str = Form('unknown'), priority: int = Form(50), check_interval_minutes: int = Form(120),
    item_selector: str = Form(''), title_selector: str = Form(''), promo_code_selector: str = Form(''),
    promo_code_attribute: str = Form(''), conditions_selector: str = Form(''),
    valid_until_selector: str = Form(''), link_selector: str = Form(''), reveal_selector: str = Form(''),
    reveal_code_attribute: str = Form(''),
):
    selector_values = (
        item_selector, title_selector, promo_code_selector, promo_code_attribute, conditions_selector,
        valid_until_selector, link_selector, reveal_selector, reveal_code_attribute,
    )
    if collector_type == "legacy_adapter" and any(value.strip() for value in selector_values):
        collector_type = "generic_web"
    try:
        with session_scope() as session:
            from src.modules.source_registry.service import update_source
            update_source(
                session, source_id, name=name, platform=platform, source_type=source_type, url=url,
                external_id=external_id or None, merchant=merchant or None, collector_type=collector_type,
                trust_level=trust_level, priority=priority, check_interval_minutes=check_interval_minutes,
                item_selector=item_selector or None, title_selector=title_selector or None,
                promo_code_selector=promo_code_selector or None, promo_code_attribute=promo_code_attribute or None,
                conditions_selector=conditions_selector or None, valid_until_selector=valid_until_selector or None,
                link_selector=link_selector or None, reveal_selector=reveal_selector or None,
                reveal_code_attribute=reveal_code_attribute or None,
            )
    except Exception as exc:
        from urllib.parse import quote
        return RedirectResponse(
            f'/sources-registry/{source_id}/edit?error=' + quote(f'{type(exc).__name__}: {exc}'),
            status_code=303,
        )
    from urllib.parse import quote
    return RedirectResponse('/sources-registry?message=' + quote('Настройки источника сохранены'), status_code=303)
@router.post('/sources-registry/{source_id}/{action}')
def source_action(source_id: int, action: str):
    if action in {'enable', 'disable'}:
        with session_scope() as session:
            set_source_enabled(session, source_id, action == 'enable')
        return RedirectResponse('/sources-registry?message=' + quote('Состояние источника обновлено'), status_code=303)
    if action == 'delete':
        with session_scope() as session:
            row = session.get(RegisteredSource, source_id)
            if row is None:
                return HTMLResponse('Source not found', status_code=404)
            if row.collector_type == 'legacy_adapter':
                return RedirectResponse('/sources-registry?error=' + quote('Legacy source нельзя удалить из registry'), status_code=303)
            session.delete(row)
        return RedirectResponse('/sources-registry?message=' + quote('Источник удалён'), status_code=303)
    if action == 'test':
        try:
            result = collect_registered_source(source_id)
            message = f'Проверка завершена: fetched={result.fetched}, offers={result.offer_signals}, errors={result.errors}'
            return RedirectResponse('/sources-registry?message=' + quote(message), status_code=303)
        except Exception as exc:
            return RedirectResponse('/sources-registry?error=' + quote(f'{type(exc).__name__}: {exc}'), status_code=303)
    return HTMLResponse('Unknown action', status_code=404)


@router.post('/sources-registry/candidates/{candidate_id}/{action}')
def candidate_action(candidate_id: int, action: str):
    if action not in {'approve', 'reject'}:
        return HTMLResponse('Unknown action', status_code=404)
    try:
        with session_scope() as session:
            review_candidate(session, candidate_id, 'approved' if action == 'approve' else 'rejected')
    except Exception as exc:
        return RedirectResponse('/sources-registry?error=' + quote(f'{type(exc).__name__}: {exc}'), status_code=303)
    return RedirectResponse('/sources-registry?message=' + quote('Кандидат обработан'), status_code=303)


@router.post('/sources-registry/keywords/add')
def keyword_add(keyword: str = Form(...), kind: str = Form('positive'), merchant: str = Form(''), priority: int = Form(50)):
    try:
        with session_scope() as session:
            add_keyword(session, keyword, kind=kind, merchant=merchant or None, priority=priority)
    except Exception as exc:
        return RedirectResponse('/sources-registry?error=' + quote(f'{type(exc).__name__}: {exc}'), status_code=303)
    return RedirectResponse('/sources-registry?message=' + quote('Ключевое слово добавлено'), status_code=303)


@router.post('/sources-registry/keywords/{keyword_id}/toggle')
def keyword_toggle(keyword_id: int):
    with session_scope() as session:
        row = session.get(SourceKeyword, keyword_id)
        if row is None:
            return HTMLResponse('Keyword not found', status_code=404)
        row.enabled = not row.enabled
    return RedirectResponse('/sources-registry?message=' + quote('Ключевое слово обновлено'), status_code=303)


@router.get('/sources-registry/export')
def registry_export():
    tmp = tempfile.NamedTemporaryFile(prefix='sources_registry_', suffix='.xlsx', delete=False)
    tmp.close()
    path = export_source_registry_xlsx(tmp.name)
    return FileResponse(
        path,
        filename='sources_registry.xlsx',
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        background=BackgroundTask(lambda: Path(path).unlink(missing_ok=True)),
    )


@router.post('/sources-registry/import')
def registry_import(file: UploadFile = File(...)):
    if not (file.filename or '').lower().endswith('.xlsx'):
        return RedirectResponse('/sources-registry?error=' + quote('Нужен файл .xlsx'), status_code=303)
    tmp = tempfile.NamedTemporaryFile(prefix='sources_registry_import_', suffix='.xlsx', delete=False)
    path = Path(tmp.name)
    try:
        tmp.write(file.file.read())
        tmp.close()
        report = import_source_registry_xlsx(path)
        if report.errors:
            return RedirectResponse('/sources-registry?error=' + quote('; '.join(report.errors[:5])), status_code=303)
        message = f'Импорт: sources={report.sources_created}, candidates={report.candidates_created_or_updated}, keywords={report.keywords_created}'
        return RedirectResponse('/sources-registry?message=' + quote(message), status_code=303)
    finally:
        try:
            tmp.close()
        except Exception:
            pass
        path.unlink(missing_ok=True)
