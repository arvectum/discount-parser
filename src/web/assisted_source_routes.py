from __future__ import annotations

import html
from urllib.parse import quote

from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from src.modules.source_registry.assisted_setup import AssistedSourceProposal, analyze_assisted_source
from src.modules.source_registry.follow_profiles import set_follow_profile
from src.modules.source_registry.image_profiles import set_image_profile
from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.service import create_source, set_source_enabled, update_source
from src.shared.db import create_session, session_scope
from src.web.setup import is_setup_complete
from src.web.source_registry_routes import _layout


def _safe(value: object, fallback: str = "—") -> str:
    raw = str(value).strip() if value is not None else ""
    return html.escape(raw or fallback, quote=True)


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


def assisted_analysis_page(url: str = Form(...)):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    try:
        proposal = analyze_assisted_source(url)
    except Exception as exc:
        return RedirectResponse('/sources-registry?error=' + quote(f'Не удалось проверить источник: {type(exc).__name__}: {exc}'), status_code=303)

    mode = "Каталог → внутренние страницы" if proposal.crawl_mode == "follow_internal" else "Прямая страница предложений"
    details = ""
    if proposal.discovered_detail_pages:
        details = (
            f'<div class="flash" style="margin-top:12px"><b>Найдено внутренних страниц:</b> '
            f'{proposal.discovered_detail_pages}. Парсер будет обходить только страницы этого же сайта.</div>'
        )
    confidence = round(proposal.confidence * 100)
    confidence_cls = "on" if proposal.confidence >= 0.85 else "warn"
    controls = ""
    if proposal.can_confirm:
        controls = f'''
        <form method="post" action="/sources-registry/confirm-auto" class="row" style="margin-top:18px">
          <input type="hidden" name="url" value="{_safe(proposal.url)}">
          <button class="btn good">Всё правильно — сохранить</button>
          <a class="btn secondary" href="/sources-registry">Отмена</a>
        </form>'''
    else:
        controls = '''<div class="warn" style="margin-top:18px">Автоматический выбор недостаточно надёжен, поэтому программа не будет сохранять сомнительную схему. Заказчику ничего настраивать вручную не нужно: такой источник можно передать разработчику для добавления шаблона.</div><div class="row" style="margin-top:12px"><a class="btn secondary" href="/sources-registry">Вернуться к источникам</a></div>'''

    body = f'''
    <div class="card">
      <h2>Автоматическая настройка источника</h2>
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
    return HTMLResponse(_layout("Автоматическая настройка", body))


def _apply_proposal(proposal: AssistedSourceProposal) -> int:
    with session_scope() as session:
        existing = session.scalar(select(RegisteredSource).where(RegisteredSource.url == proposal.url))
        if existing is None:
            source = create_source(
                session,
                name=proposal.name,
                platform="website",
                source_type="promotion_page",
                url=proposal.url,
                collector_type="generic_web",
                trust_level="unknown",
                priority=50,
                check_interval_minutes=120,
                enabled=False,
                item_selector=proposal.item_selector,
                title_selector=proposal.title_selector,
                promo_code_selector=proposal.promo_code_selector,
                promo_code_attribute=proposal.promo_code_attribute,
                conditions_selector=proposal.conditions_selector,
                valid_until_selector=proposal.valid_until_selector,
                link_selector=proposal.link_selector,
            )
        else:
            source = update_source(
                session,
                existing.id,
                name=proposal.name,
                platform="website",
                source_type="promotion_page",
                collector_type="generic_web",
                item_selector=proposal.item_selector,
                title_selector=proposal.title_selector,
                promo_code_selector=proposal.promo_code_selector,
                promo_code_attribute=proposal.promo_code_attribute,
                conditions_selector=proposal.conditions_selector,
                valid_until_selector=proposal.valid_until_selector,
                link_selector=proposal.link_selector,
            )
        source_id = int(source.id)

    if proposal.image_selector:
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
    return source_id


def confirm_assisted_source(url: str = Form(...)):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    try:
        # Re-run analysis instead of trusting hidden technical parameters from the browser.
        proposal = analyze_assisted_source(url)
        if not proposal.can_confirm:
            raise ValueError("Автоматическая схема не прошла проверку уверенности.")
        _apply_proposal(proposal)
    except Exception as exc:
        return RedirectResponse('/sources-registry?error=' + quote(f'Источник не сохранён: {type(exc).__name__}: {exc}'), status_code=303)
    return RedirectResponse(
        '/sources-registry?message=' + quote('Источник автоматически настроен, проверен и включён. Ручная настройка не требуется.'),
        status_code=303,
    )
