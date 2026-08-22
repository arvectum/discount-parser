from __future__ import annotations

import html
import logging
from urllib.parse import quote

from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from src.modules.source_registry.assisted_setup import AssistedSourceProposal, analyze_assisted_source
from src.modules.source_registry.follow_profiles import set_follow_profile
from src.modules.source_registry.image_profiles import set_image_profile
from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.runner import collect_registered_source
from src.modules.source_registry.service import set_source_enabled, update_source
from src.modules.source_registry.auto_setup import normalize_source_url
from src.shared.db import create_session, session_scope
from src.shared.network import NetworkRouteError
from src.web.source_registry_routes import _layout
from src.web.setup import is_setup_complete

logger = logging.getLogger(__name__)


def _safe(value: object, fallback: str = "—") -> str:
    raw = str(value).strip() if value is not None else ""
    return html.escape(raw or fallback, quote=True)


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, NetworkRouteError):
        return (
            "Discount Parser не смог подключиться к сайту из приложения. "
            "Программа автоматически проверила обычное подключение и системный прокси Windows. "
            "Если сайт при этом открывается в браузере, повторите проверку после обновления приложения; "
            "ручная разметка HTML для решения этой ошибки не нужна."
        )
    return "Автоматическая настройка не завершена. Источник не изменён; повторите проверку или передайте ссылку разработчику."


def _preview_table(proposal: AssistedSourceProposal) -> str:
    rows: list[str] = []
    for index, item in enumerate(proposal.previews, 1):
        link = f'<a target="_blank" rel="noopener" href="{_safe(item.url)}">открыть</a>' if item.url else "—"
        rows.append(
            "<tr>"
            f"<td>{index}</td><td>{_safe(item.title)}</td><td>{_safe(item.promo_code)}</td>"
            f"<td>{_safe(item.valid_until)}</td><td>{_safe(item.excerpt)}</td><td>{link}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="6">Надёжный предпросмотр не получен.</td></tr>')
    return (
        '<div class="scroll"><table class="table"><thead><tr>'
        '<th>#</th><th>Название</th><th>Промокод</th><th>Срок</th><th>Что будет сохранено</th><th>Ссылка</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _proposal_page(
    proposal: AssistedSourceProposal,
    *,
    source_id: int | None = None,
    proposed_name: str = "",
) -> HTMLResponse:
    mode = "Каталог → внутренние страницы" if proposal.crawl_mode == "follow_internal" else "Прямая страница предложений"
    confidence = round(proposal.confidence * 100)
    confidence_cls = "on" if proposal.confidence >= 0.85 else "warn"
    details = ""
    if proposal.discovered_detail_pages:
        details = (
            f'<div class="flash" style="margin-top:12px"><b>Найдено внутренних страниц:</b> '
            f'{proposal.discovered_detail_pages}. Парсер будет обходить только страницы этого же сайта.</div>'
        )

    is_existing = source_id is not None
    title = "Автоматическая перенастройка источника" if is_existing else "Автоматическая настройка источника"
    cancel = f"/sources-registry/{source_id}/settings" if is_existing else "/sources-registry"
    if proposal.can_confirm:
        if is_existing:
            controls = f'''
            <form method="post" action="/sources-registry/{source_id}/confirm-auto" class="row" style="margin-top:18px">
              <input type="hidden" name="url" value="{_safe(proposal.url, '')}">
              <input type="hidden" name="name" value="{_safe(proposed_name, '')}">
              <button class="btn good">Всё правильно — применить</button>
              <a class="btn secondary" href="{cancel}">Отмена</a>
            </form>'''
        else:
            controls = f'''
            <form method="post" action="/sources-registry/confirm-auto" class="row" style="margin-top:18px">
              <input type="hidden" name="url" value="{_safe(proposal.url, '')}">
              <button class="btn good">Всё правильно — сохранить</button>
              <a class="btn secondary" href="{cancel}">Отмена</a>
            </form>'''
    else:
        controls = (
            '<div class="warn" style="margin-top:18px">Автоматический выбор недостаточно надёжен, поэтому программа ничего не сохранит. '
            'Ручные CSS-селекторы заказчику вводить не нужно — такой источник передаётся разработчику для добавления шаблона.</div>'
            f'<div class="row" style="margin-top:12px"><a class="btn secondary" href="{cancel}">Вернуться</a></div>'
        )

    body = f'''
    <div class="card">
      <h2>{title}</h2>
      <div class="muted">{_safe(proposal.url)}</div>
      <div class="grid" style="margin-top:14px">
        <div class="card" style="margin:0"><b>{_safe(mode)}</b><div class="muted">выбранный режим</div></div>
        <div class="card" style="margin:0"><span class="pill {confidence_cls}">{confidence}%</span><div class="muted" style="margin-top:6px">уверенность настройки</div></div>
      </div>
      <div class="flash" style="margin-top:14px">{_safe(proposal.explanation)}</div>
      {details}
    </div>
    <div class="card">
      <h2>Проверьте результат</h2>
      <div class="muted" style="margin-bottom:12px">Ничего копировать из HTML не нужно. Проверьте только, что данные попали в правильные графы.</div>
      {_preview_table(proposal)}
      {controls}
    </div>'''
    return _layout(title, body)


def customer_source_analysis_page(url: str = Form(...)):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    try:
        proposal = analyze_assisted_source(url)
        with create_session() as session:
            existing = session.scalar(select(RegisteredSource).where(RegisteredSource.url == proposal.url))
            existing_id = int(existing.id) if existing is not None else None
        return _proposal_page(proposal, source_id=existing_id)
    except Exception as exc:
        logger.warning("customer_auto_source_analysis_failed error=%s", type(exc).__name__)
        return RedirectResponse('/sources-registry?error=' + quote(_friendly_error(exc)), status_code=303)


def customer_confirm_assisted_source(url: str = Form(...)):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    try:
        from src.web.assisted_source_routes import _apply_proposal

        proposal = analyze_assisted_source(url)
        if not proposal.can_confirm:
            raise ValueError("automatic proposal confidence gate failed")
        _apply_proposal(proposal)
    except Exception as exc:
        logger.warning("customer_auto_source_confirm_failed error=%s", type(exc).__name__)
        return RedirectResponse('/sources-registry?error=' + quote(_friendly_error(exc)), status_code=303)
    return RedirectResponse(
        '/sources-registry?message=' + quote('Источник автоматически настроен, проверен и включён.'),
        status_code=303,
    )


def customer_existing_source_analysis(source_id: int):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    with create_session() as session:
        source = session.get(RegisteredSource, source_id)
        if source is None:
            return HTMLResponse("Source not found", status_code=404)
        url = str(source.url or "")
    try:
        proposal = analyze_assisted_source(url)
        return _proposal_page(proposal, source_id=source_id)
    except Exception as exc:
        logger.warning("customer_existing_source_analysis_failed source_id=%s error=%s", source_id, type(exc).__name__)
        return RedirectResponse(
            f'/sources-registry/{source_id}/settings?error=' + quote(_friendly_error(exc)),
            status_code=303,
        )


def _apply_existing_proposal(
    proposal: AssistedSourceProposal,
    *,
    source_id: int,
    name: str = "",
) -> None:
    with session_scope() as session:
        source = session.get(RegisteredSource, source_id)
        if source is None:
            raise ValueError("Источник не найден")
        values: dict[str, object] = {
            "platform": "website",
            "source_type": "promotion_page",
            "url": proposal.url,
            "collector_type": "generic_web",
            "item_selector": proposal.item_selector,
            "title_selector": proposal.title_selector,
            "promo_code_selector": proposal.promo_code_selector,
            "promo_code_attribute": proposal.promo_code_attribute,
            "conditions_selector": proposal.conditions_selector,
            "valid_until_selector": proposal.valid_until_selector,
            "link_selector": proposal.link_selector,
            "reveal_selector": None,
            "reveal_code_attribute": None,
        }
        if name.strip():
            values["name"] = name.strip()
        update_source(session, source_id, **values)

    set_image_profile(
        source_id,
        image_selector=proposal.image_selector,
        image_attribute=proposal.image_attribute,
    )
    set_follow_profile(
        source_id,
        crawl_mode=proposal.crawl_mode,
        listing_item_selector=proposal.listing_item_selector,
        detail_link_selector=proposal.detail_link_selector,
        detail_url_contains=proposal.detail_url_contains,
        max_detail_pages=100,
    )
    with session_scope() as session:
        set_source_enabled(session, source_id, True)


def customer_confirm_existing_source(
    source_id: int,
    url: str = Form(""),
    name: str = Form(""),
):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    try:
        with create_session() as session:
            source = session.get(RegisteredSource, source_id)
            if source is None:
                return HTMLResponse("Source not found", status_code=404)
            current_url = str(source.url or "")
        target_url = normalize_source_url(url or current_url)
        proposal = analyze_assisted_source(target_url)
        if not proposal.can_confirm:
            raise ValueError("automatic proposal confidence gate failed")
        _apply_existing_proposal(proposal, source_id=source_id, name=name)
    except Exception as exc:
        logger.warning("customer_existing_source_confirm_failed source_id=%s error=%s", source_id, type(exc).__name__)
        return RedirectResponse(
            f'/sources-registry/{source_id}/settings?error=' + quote(_friendly_error(exc)),
            status_code=303,
        )
    return RedirectResponse(
        '/sources-registry?message=' + quote('Источник автоматически перенастроен, проверен и включён.'),
        status_code=303,
    )


def customer_source_settings_page(
    source_id: int,
    error: str | None = None,
    message: str | None = None,
):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    with create_session() as session:
        source = session.get(RegisteredSource, source_id)
        if source is None:
            return HTMLResponse('Source not found', status_code=404)
        snapshot = {"id": int(source.id), "name": source.name, "url": source.url}

    err = f'<div class="err">{_safe(error)}</div>' if error else ""
    flash = f'<div class="flash">{_safe(message)}</div>' if message else ""
    body = f'''{flash}{err}
    <div class="card">
      <h2>{_safe(snapshot['name'], 'Источник')}</h2>
      <div class="muted">Измените название или ссылку. Если ссылка меняется, Discount Parser сначала сам определит структуру и покажет результат — изменения применятся только после вашего подтверждения.</div>
      <form method="post" action="/sources-registry/{snapshot['id']}/settings" style="margin-top:16px">
        <div class="grid">
          <div class="field"><label>Название</label><input name="name" value="{_safe(snapshot['name'], '')}" placeholder="Можно оставить как есть"></div>
          <div class="field"><label>Ссылка</label><input name="url" value="{_safe(snapshot['url'], '')}" required></div>
        </div>
        <div class="row" style="margin-top:16px"><button class="btn good">Продолжить</button><a class="btn secondary" href="/sources-registry">Отмена</a></div>
      </form>
    </div>
    <div class="card">
      <h2>Перенастроить источник автоматически</h2>
      <div class="muted">Используйте это после изменения сайта или если старые настройки собирают данные неправильно. Парсер сам выберет поля; вам останется только проверить несколько строк и подтвердить.</div>
      <form method="post" action="/sources-registry/{snapshot['id']}/analyze-auto" style="margin-top:14px"><button class="btn good">Перенастроить автоматически</button></form>
    </div>
    <div class="card"><div class="muted">Ручные CSS-селекторы и HTML заказчику вводить не требуется. Если автоматическая настройка не уверена в результате, источник не будет изменён.</div></div>'''
    return _layout("Изменить источник", body)


def customer_source_settings_save(
    source_id: int,
    name: str = Form(''),
    url: str = Form(...),
):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    try:
        normalized = normalize_source_url(url)
        with create_session() as session:
            source = session.get(RegisteredSource, source_id)
            if source is None:
                return HTMLResponse('Source not found', status_code=404)
            old_url = str(source.url or "")
        if normalized != old_url:
            proposal = analyze_assisted_source(normalized)
            return _proposal_page(proposal, source_id=source_id, proposed_name=name)
        with session_scope() as session:
            values: dict[str, object] = {}
            if name.strip():
                values["name"] = name.strip()
            if values:
                update_source(session, source_id, **values)
    except Exception as exc:
        logger.warning("customer_source_settings_save_failed source_id=%s error=%s", source_id, type(exc).__name__)
        return RedirectResponse(
            f'/sources-registry/{source_id}/settings?error=' + quote(_friendly_error(exc)),
            status_code=303,
        )
    return RedirectResponse('/sources-registry?message=' + quote('Источник обновлён'), status_code=303)


def customer_mapping_redirect(source_id: int):
    message = (
        "Ручная разметка полей больше не нужна в обычной работе. "
        "Запустите автоматическую перенастройку и только проверьте результат."
    )
    return RedirectResponse(
        f'/sources-registry/{source_id}/settings?message=' + quote(message),
        status_code=303,
    )


def customer_source_test(source_id: int):
    try:
        result = collect_registered_source(source_id)
        message = f'Проверка завершена: найдено {result.fetched}, распознано предложений {result.offer_signals}, ошибок {result.errors}.'
        return RedirectResponse('/sources-registry?message=' + quote(message), status_code=303)
    except Exception as exc:
        logger.warning("customer_source_test_failed source_id=%s error=%s", source_id, type(exc).__name__)
        return RedirectResponse('/sources-registry?error=' + quote(_friendly_error(exc)), status_code=303)
