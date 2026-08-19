from __future__ import annotations

import html
from urllib.parse import quote

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from src.modules.source_registry.auto_setup import AutoSourceAnalysis, AutoSourceSetupError, analyze_source_url, normalize_source_url
from src.modules.source_registry.models import RegisteredSource, SourceCandidate, SourceKeyword
from src.modules.source_registry.service import create_source, update_source
from src.modules.source_registry.xlsx import import_source_registry_xlsx
from src.shared.db import create_session, session_scope
from src.web.setup import is_setup_complete
from src.web.source_registry_routes import _layout


router = APIRouter()


_STATUS_LABELS = {
    "healthy": ("Работает", "on"),
    "degraded": ("Есть проблема", "warn"),
    "blocked": ("Недоступен", "off"),
    "requires_credentials": ("Нужен вход", "warn"),
    "disabled": ("Выключен", "off"),
    "unknown": ("Готов к проверке", "warn"),
}


def _safe(value: object, fallback: str = "—") -> str:
    raw = str(value).strip() if value is not None else ""
    return html.escape(raw or fallback, quote=True)


def _require_setup():
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    return None


def _source_rows() -> str:
    with create_session() as session:
        rows = session.scalars(select(RegisteredSource).order_by(RegisteredSource.name, RegisteredSource.id)).all()
        snapshots = [
            {
                "id": row.id,
                "name": row.name,
                "url": row.url,
                "enabled": row.enabled,
                "status": row.status,
                "last_success_at": row.last_success_at,
                "last_error": row.last_error,
                "collector_type": row.collector_type,
            }
            for row in rows
        ]

    rendered: list[str] = []
    for row in snapshots:
        status_key = "disabled" if not row["enabled"] else str(row["status"] or "unknown")
        status_label, status_cls = _STATUS_LABELS.get(status_key, ("Готов к проверке", "warn"))
        action = "disable" if row["enabled"] else "enable"
        action_label = "Выключить" if row["enabled"] else "Включить"
        raw_url = str(row["url"] or "").strip()
        url_html = _safe(raw_url)
        if raw_url.startswith(("http://", "https://")):
            url_html = f'<a href="{html.escape(raw_url, quote=True)}" target="_blank" rel="noopener">{_safe(raw_url[:70])}</a>'
        last_ok = _safe(row["last_success_at"], "Ещё не запускался")
        problem = str(row["last_error"] or "").strip()
        problem_html = f'<div class="muted" style="margin-top:4px">{_safe(problem[:120])}</div>' if problem else ""
        delete = "" if row["collector_type"] == "legacy_adapter" else (
            f'<form method="post" action="/sources-registry/{int(row["id"])}/delete" '
            'onsubmit="return confirm(\'Удалить источник?\')"><button class="btn bad">Удалить</button></form>'
        )
        rendered.append(
            "<tr>"
            f"<td><b>{_safe(row['name'], 'Источник')}</b></td>"
            f"<td>{url_html}</td>"
            f"<td><span class='pill {status_cls}'>{status_label}</span>{problem_html}</td>"
            f"<td>{last_ok}</td>"
            "<td><div class='row'>"
            f"<form method='post' action='/sources-registry/{int(row['id'])}/test'><button class='btn good'>Проверить</button></form>"
            f"<a class='btn secondary' href='/sources-registry/{int(row['id'])}/settings'>Изменить</a>"
            f"<form method='post' action='/sources-registry/{int(row['id'])}/{action}'><button class='btn secondary'>{action_label}</button></form>"
            f"{delete}</div></td></tr>"
        )
    return "".join(rendered) or '<tr><td colspan="5">Источников пока нет. Добавьте первый источник по ссылке ниже.</td></tr>'


def _specialist_block() -> str:
    with create_session() as session:
        candidates = session.scalars(
            select(SourceCandidate).where(SourceCandidate.status == "new").order_by(SourceCandidate.confidence.desc(), SourceCandidate.id)
        ).all()
        keywords = session.scalars(
            select(SourceKeyword).order_by(SourceKeyword.enabled.desc(), SourceKeyword.priority.desc(), SourceKeyword.keyword)
        ).all()

    candidate_rows = "".join(
        "<tr>"
        f"<td>{_safe(item.name)}</td><td>{_safe(item.url)}</td><td>{float(item.confidence or 0):.2f}</td>"
        f"<td><div class='row'><form method='post' action='/sources-registry/candidates/{item.id}/approve'><button class='btn good'>Одобрить</button></form>"
        f"<form method='post' action='/sources-registry/candidates/{item.id}/reject'><button class='btn bad'>Отклонить</button></form></div></td></tr>"
        for item in candidates
    ) or '<tr><td colspan="4">Новых кандидатов нет.</td></tr>'
    keyword_rows = "".join(
        "<tr>"
        f"<td>{_safe(item.keyword)}</td><td>{_safe(item.kind)}</td><td>{int(item.priority or 0)}</td>"
        f"<td><form method='post' action='/sources-registry/keywords/{item.id}/toggle'><button class='btn secondary'>Переключить</button></form></td></tr>"
        for item in keywords[:200]
    )
    return f'''
    <details class="card">
      <summary style="cursor:pointer;font-weight:700">Для специалиста — служебные инструменты</summary>
      <div class="muted" style="margin:12px 0">Эти настройки не нужны для обычного добавления источника.</div>
      <div class="row">
        <a class="btn secondary" href="/sources-registry/export">Скачать реестр XLSX</a>
        <form method="post" action="/sources-registry/import" enctype="multipart/form-data">
          <input type="file" name="file" accept=".xlsx" required><button class="btn secondary">Импорт XLSX</button>
        </form>
      </div>
      <h3 style="margin-top:18px">Кандидаты</h3>
      <div class="scroll"><table class="table"><thead><tr><th>Название</th><th>URL</th><th>Уверенность</th><th></th></tr></thead><tbody>{candidate_rows}</tbody></table></div>
      <h3 style="margin-top:18px">Ключевые слова</h3>
      <form method="post" action="/sources-registry/keywords/add"><div class="row">
        <input name="keyword" placeholder="слово или фраза" required style="padding:9px;min-width:250px">
        <select name="kind" style="padding:9px"><option value="strong_positive">важное</option><option value="positive" selected>обычное</option><option value="negative">исключение</option><option value="merchant">магазин</option><option value="custom">другое</option></select>
        <input name="priority" type="number" value="50" min="0" max="100" style="padding:9px;width:100px"><button class="btn good">Добавить</button>
      </div></form>
      <div class="scroll" style="margin-top:12px"><table class="table"><thead><tr><th>Слово</th><th>Тип</th><th>Приоритет</th><th></th></tr></thead><tbody>{keyword_rows}</tbody></table></div>
    </details>'''


def friendly_registry_page(message: str | None = None, error: str | None = None):
    redirect = _require_setup()
    if redirect:
        return redirect
    flash = f'<div class="flash">{_safe(message)}</div>' if message else ""
    err = f'<div class="err">{_safe(error)}</div>' if error else ""
    body = f'''{flash}{err}
    <div class="card">
      <h2>Добавить источник</h2>
      <div class="muted">Вставьте ссылку. Discount Parser сам определит тип источника, попробует найти предложения и покажет пример до добавления.</div>
      <form method="post" action="/sources-registry/analyze" style="margin-top:14px">
        <div class="row">
          <input name="url" placeholder="example.ru/promokody или https://t.me/channel" required autocomplete="url" style="flex:1;min-width:280px;padding:12px;border:1px solid #cbd5e1;border-radius:9px">
          <button class="btn good">Проверить источник</button>
        </div>
      </form>
      <div class="muted" style="margin-top:10px">HTML, CSS, атрибуты и другие технические параметры вводить не нужно.</div>
    </div>
    <div class="card">
      <div class="row" style="justify-content:space-between"><div><h2 style="margin-bottom:4px">Ваши источники</h2><div class="muted">Проверяйте, включайте и выключайте их обычными кнопками.</div></div></div>
      <div class="scroll" style="margin-top:12px"><table class="table"><thead><tr><th>Источник</th><th>Адрес</th><th>Состояние</th><th>Последний успешный сбор</th><th>Действия</th></tr></thead><tbody>{_source_rows()}</tbody></table></div>
    </div>
    {_specialist_block()}'''
    return _layout("Источники", body)


def _analysis_page(analysis: AutoSourceAnalysis) -> HTMLResponse:
    if analysis.confidence >= 0.8:
        verdict = "Структура источника определена автоматически. Проверьте несколько примеров ниже."
        verdict_class = "flash"
    else:
        verdict = "Источник нестандартный. Мы нашли данные, но лучше внимательно проверить примеры перед добавлением."
        verdict_class = "warn"

    preview_cards: list[str] = []
    for item in analysis.items:
        promo = f'<div><b>Промокод:</b> {_safe(item.promo_code)}</div>' if item.promo_code else '<div class="muted">Промокод в этом примере не найден</div>'
        valid = f'<div><b>Срок:</b> {_safe(item.valid_until)}</div>' if item.valid_until else ""
        link = f'<a href="{html.escape(item.url, quote=True)}" target="_blank" rel="noopener">Открыть предложение</a>' if item.url else ""
        preview_cards.append(
            f'''<div class="card" style="margin-top:10px"><h3>{_safe(item.title)}</h3>{promo}{valid}<div class="muted" style="margin-top:8px">{_safe(item.excerpt[:260])}</div><div style="margin-top:8px">{link}</div></div>'''
        )

    if not analysis.can_add:
        controls = '<div class="err">Не удалось найти предложения на странице. Источник не добавлен.</div><a class="btn secondary" href="/sources-registry">Попробовать другую ссылку</a>'
    else:
        controls = f'''
        <form method="post" action="/sources-registry/add-auto" class="row" style="margin-top:16px">
          <input type="hidden" name="url" value="{html.escape(analysis.url, quote=True)}">
          <button class="btn good">Всё правильно — добавить источник</button>
          <a class="btn secondary" href="/sources-registry">Попробовать другую ссылку</a>
        </form>'''

    body = f'''
    <div class="card">
      <h2>{_safe(analysis.name)}</h2>
      <div class="muted">{_safe(analysis.url)}</div>
      <div class="{verdict_class}" style="margin-top:14px">{verdict}</div>
      <div class="grid" style="margin-top:14px">
        <div class="card" style="margin:0"><b>{analysis.fetched}</b><div class="muted">предложений найдено</div></div>
        <div class="card" style="margin:0"><b>{analysis.promo_codes_found}</b><div class="muted">промокодов в примерах</div></div>
        <div class="card" style="margin:0"><b>{analysis.dates_found}</b><div class="muted">сроков действия в примерах</div></div>
      </div>
    </div>
    <h2 style="margin-top:20px">Примеры найденного</h2>
    {''.join(preview_cards) or '<div class="card">Примеры не найдены.</div>'}
    {controls}'''
    return _layout("Проверка источника", body)


@router.post('/sources-registry/analyze', response_class=HTMLResponse)
def analyze_source_route(url: str = Form(...)):
    redirect = _require_setup()
    if redirect:
        return redirect
    try:
        normalized = normalize_source_url(url)
        with create_session() as session:
            existing = session.scalar(select(RegisteredSource).where(RegisteredSource.url == normalized))
            if existing is not None:
                return RedirectResponse(
                    f'/sources-registry?message=' + quote('Этот источник уже добавлен'), status_code=303
                )
        return _analysis_page(analyze_source_url(normalized))
    except AutoSourceSetupError as exc:
        return friendly_registry_page(error=str(exc))


@router.post('/sources-registry/add-auto')
def add_auto_source_route(url: str = Form(...)):
    redirect = _require_setup()
    if redirect:
        return redirect
    try:
        analysis = analyze_source_url(url)
        if not analysis.can_add:
            raise AutoSourceSetupError("На странице не удалось найти предложения. Источник не добавлен.")
        with session_scope() as session:
            existing = session.scalar(select(RegisteredSource).where(RegisteredSource.url == analysis.url))
            if existing is None:
                create_source(
                    session,
                    name=analysis.name,
                    platform=analysis.platform,
                    source_type=analysis.source_type,
                    url=analysis.url,
                    external_id=analysis.external_id,
                    collector_type=analysis.collector_type,
                    trust_level="unknown",
                    priority=50,
                    check_interval_minutes=120,
                )
    except Exception as exc:
        message = str(exc) if isinstance(exc, AutoSourceSetupError) else f'{type(exc).__name__}: {exc}'
        return RedirectResponse('/sources-registry?error=' + quote(message), status_code=303)
    return RedirectResponse('/sources-registry?message=' + quote('Источник добавлен и готов к сбору'), status_code=303)


@router.get('/sources-registry/{source_id}/settings', response_class=HTMLResponse)
def source_settings_page(source_id: int, error: str | None = None):
    redirect = _require_setup()
    if redirect:
        return redirect
    with create_session() as session:
        source = session.get(RegisteredSource, source_id)
        if source is None:
            return HTMLResponse('Source not found', status_code=404)
        snapshot = {
            "id": source.id,
            "name": source.name,
            "url": source.url,
        }
    err = f'<div class="err">{_safe(error)}</div>' if error else ""
    body = f'''{err}
    <div class="card">
      <h2>{_safe(snapshot['name'], 'Источник')}</h2>
      <div class="muted">Обычно здесь достаточно изменить название или ссылку. Если ссылка меняется, тип источника будет определён автоматически.</div>
      <form method="post" action="/sources-registry/{snapshot['id']}/settings" style="margin-top:16px">
        <div class="grid">
          <div class="field"><label>Название</label><input name="name" value="{_safe(snapshot['name'], '')}" placeholder="Можно оставить как есть"></div>
          <div class="field"><label>Ссылка</label><input name="url" value="{_safe(snapshot['url'], '')}" required></div>
        </div>
        <div class="row" style="margin-top:16px"><button class="btn good">Сохранить</button><a class="btn secondary" href="/sources-registry">Отмена</a></div>
      </form>
    </div>
    <details class="card"><summary style="cursor:pointer;font-weight:700">Для специалиста — технические настройки</summary>
      <div class="muted" style="margin:12px 0">CSS-селекторы, collector, приоритет и другие внутренние параметры нужны только для ручной диагностики нестандартного сайта.</div>
      <a class="btn secondary" href="/sources-registry/{snapshot['id']}/edit">Открыть технические настройки</a>
    </details>'''
    return _layout("Изменить источник", body)


@router.post('/sources-registry/{source_id}/settings')
def source_settings_save(source_id: int, name: str = Form(''), url: str = Form(...)):
    try:
        normalized = normalize_source_url(url)
        with create_session() as session:
            current = session.get(RegisteredSource, source_id)
            if current is None:
                return HTMLResponse('Source not found', status_code=404)
            old_url = current.url
        values: dict[str, object] = {"url": normalized}
        if name.strip():
            values["name"] = name.strip()
        if normalized != old_url:
            analysis = analyze_source_url(normalized)
            if not analysis.can_add:
                raise AutoSourceSetupError("Новая ссылка не прошла автоматическую проверку.")
            values.update({
                "name": name.strip() or analysis.name,
                "platform": analysis.platform,
                "source_type": analysis.source_type,
                "external_id": analysis.external_id,
                "collector_type": analysis.collector_type,
                "item_selector": None,
                "title_selector": None,
                "promo_code_selector": None,
                "promo_code_attribute": None,
                "conditions_selector": None,
                "valid_until_selector": None,
                "link_selector": None,
                "reveal_selector": None,
                "reveal_code_attribute": None,
            })
        with session_scope() as session:
            update_source(session, source_id, **values)
    except Exception as exc:
        message = str(exc) if isinstance(exc, AutoSourceSetupError) else f'{type(exc).__name__}: {exc}'
        return RedirectResponse(f'/sources-registry/{source_id}/settings?error=' + quote(message), status_code=303)
    return RedirectResponse('/sources-registry?message=' + quote('Источник обновлён'), status_code=303)
