from __future__ import annotations

import html
from urllib.parse import quote, urlparse

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from src.modules.source_registry.collectors import GenericWebCollector
from src.modules.source_registry.follow_profiles import FollowProfile, extract_internal_detail_urls, get_follow_profile, set_follow_profile
from src.modules.source_registry.image_profiles import set_image_profile
from src.modules.source_registry.manual_profile import normalize_manual_profile, preview_manual_profile_html
from src.modules.source_registry.service import set_source_enabled, update_source
from src.shared.db import session_scope
from src.web.manual_mapping_routes import _source_snapshot
from src.web.setup import is_setup_complete
from src.web.source_registry_routes import _layout


def _safe(value: object, fallback: str = "") -> str:
    raw = str(value).strip() if value is not None else ""
    return html.escape(raw or fallback, quote=True)


def _mode_profile(
    *,
    crawl_mode: str,
    listing_item_selector: str,
    detail_link_selector: str,
    detail_url_contains: str,
    max_detail_pages: int,
) -> FollowProfile:
    mode = crawl_mode if crawl_mode in {"direct", "follow_internal"} else "direct"
    if mode == "direct":
        return FollowProfile(crawl_mode="direct")
    from src.modules.source_registry.manual_profile import generalize_container_selector, relative_field_selector

    sample = listing_item_selector.strip()
    listing = generalize_container_selector(sample) if sample else None
    link = relative_field_selector(sample, detail_link_selector) if sample else detail_link_selector.strip() or None
    if not link:
        raise ValueError("Укажите selector внутренней кнопки/ссылки «Все промокоды».")
    return FollowProfile(
        crawl_mode="follow_internal",
        listing_item_selector=listing,
        detail_link_selector=link,
        detail_url_contains=detail_url_contains.strip() or None,
        max_detail_pages=max(1, min(int(max_detail_pages or 100), 500)),
    )


def _resolve_preview_page(collector: GenericWebCollector, snapshot: dict[str, object], follow: FollowProfile, sample_detail_url: str) -> tuple[str, str, list[str]]:
    source_url = str(snapshot["url"])
    route = str(snapshot.get("network_policy") or "auto")
    if follow.crawl_mode == "direct":
        response = collector._get(source_url, route=route)
        return str(response.url), response.text, []

    entry_response = collector._get(source_url, route=route)
    from bs4 import BeautifulSoup

    entry_soup = BeautifulSoup(entry_response.text, "html.parser")
    for tag in entry_soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    detail_urls = extract_internal_detail_urls(entry_soup, entry_url=str(entry_response.url), profile=follow)
    if not detail_urls:
        raise ValueError("По selector каталога не найдено внутренних страниц. Внешние кнопки активации намеренно игнорируются.")

    requested = sample_detail_url.strip()
    if requested:
        base_host = (urlparse(source_url).hostname or "").casefold().removeprefix("www.")
        requested_host = (urlparse(requested).hostname or "").casefold().removeprefix("www.")
        if requested_host != base_host:
            raise ValueError("Пример внутренней страницы должен быть на том же сайте.")
        detail_url = requested
    else:
        detail_url = detail_urls[0]
    response = collector._get(detail_url, route=route)
    return str(response.url), response.text, detail_urls


def _field(label: str, name: str, value: str, help_text: str, placeholder: str = "") -> str:
    return f'''<div class="field" style="margin-bottom:13px"><label>{_safe(label)}</label><input name="{_safe(name)}" value="{_safe(value)}" placeholder="{_safe(placeholder)}" style="font-family:ui-monospace,Consolas,monospace"><div class="muted" style="font-size:12px;margin-top:4px">{_safe(help_text)}</div></div>'''


def _preview(items, *, detail_page_url: str, discovered_urls: list[str]) -> str:
    rows = []
    for index, item in enumerate(items, 1):
        link = f'<a target="_blank" rel="noopener" href="{_safe(item.link)}">открыть</a>' if item.link else "—"
        image = "есть" if item.image_url else "—"
        discount = f"{_safe(item.discount_percent)}%" if item.discount_percent else _safe(item.amount_hint, "—")
        rows.append(
            f"<tr><td>{index}</td><td>{_safe(item.title, '—')}</td><td>{_safe(item.promo_code, '—')}</td><td>{discount}</td><td>{_safe(item.conditions, '—')}</td><td>{_safe(item.valid_until, '—')}</td><td>{link}</td><td>{image}</td></tr>"
        )
    discovered = ""
    if discovered_urls:
        sample_links = "".join(f'<li><a target="_blank" rel="noopener" href="{_safe(url)}">{_safe(url)}</a></li>' for url in discovered_urls[:5])
        discovered = f'<div class="flash"><b>Внутренние страницы найдены:</b> {len(discovered_urls)}. Парсер будет обходить только ссылки этого же сайта; внешние «Активировать» не используются для обхода.<ul>{sample_links}</ul></div>'
    return f'''<div class="card"><h2>Проверка схемы</h2>{discovered}<div>Шаблон проверен на: <a target="_blank" rel="noopener" href="{_safe(detail_page_url)}">{_safe(detail_page_url)}</a></div><div class="scroll" style="margin-top:12px"><table class="table"><thead><tr><th>#</th><th>Название</th><th>Промокод</th><th>Скидка</th><th>Условия</th><th>Срок</th><th>Ссылка</th><th>Фото</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>'''


def mapping_page_v2(
    source_id: int,
    *,
    values: dict[str, str] | None = None,
    preview_items=None,
    detail_page_url: str = "",
    discovered_urls: list[str] | None = None,
    message: str | None = None,
    error: str | None = None,
):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    snapshot = _source_snapshot(source_id)
    if snapshot is None:
        return HTMLResponse("Source not found", status_code=404)
    persisted_follow = get_follow_profile(source_id)
    values = values or {}

    def value(name: str, fallback: object = "") -> str:
        return values.get(name, str(fallback or ""))

    crawl_mode = value("crawl_mode", persisted_follow.crawl_mode) or "direct"
    listing = value("listing_item_selector", persisted_follow.listing_item_selector)
    detail_link = value("detail_link_selector", persisted_follow.detail_link_selector)
    detail_contains = value("detail_url_contains", persisted_follow.detail_url_contains)
    max_pages = value("max_detail_pages", persisted_follow.max_detail_pages or 100)
    sample_detail = value("sample_detail_url", detail_page_url)

    mapping_names = (
        "item_selector", "title_selector", "promo_code_selector", "promo_code_attribute",
        "conditions_selector", "valid_until_selector", "link_selector", "image_selector", "image_attribute",
    )
    mapped = {name: value(name, snapshot.get(name)) for name in mapping_names}
    flash = f'<div class="flash">{_safe(message)}</div>' if message else ""
    err = f'<div class="err">{_safe(error)}</div>' if error else ""

    direct_selected = " selected" if crawl_mode == "direct" else ""
    follow_selected = " selected" if crawl_mode == "follow_internal" else ""
    form_fields = ''.join([
        _field("Карточка предложения на странице-шаблоне", "item_selector", mapped["item_selector"], "Copy selector целой карточки. Конечный nth-child будет автоматически убран."),
        _field("Название → Название", "title_selector", mapped["title_selector"], "Copy selector текста названия внутри примерной карточки."),
        _field("Промокод → Промокод", "promo_code_selector", mapped["promo_code_selector"], "Copy selector кода."),
        _field("Атрибут промокода", "promo_code_attribute", mapped["promo_code_attribute"], "Оставьте пустым, если код виден текстом; иначе data-code/value и т.п."),
        _field("Условия/описание → Условия", "conditions_selector", mapped["conditions_selector"], "Из этого же текста извлекается процент/сумма скидки."),
        _field("Срок → Действует до", "valid_until_selector", mapped["valid_until_selector"], "Элемент с датой/фразой о сроке."),
        _field("Ссылка → Ссылка", "link_selector", mapped["link_selector"], "Может быть и внешняя ссылка рекламодателя; она сохраняется как поле, но crawler по ней не ходит."),
        _field("Фото → Фото", "image_selector", mapped["image_selector"], "Selector картинки внутри карточки."),
        _field("Атрибут фото", "image_attribute", mapped["image_attribute"], "Обычно пусто; для lazy-load data-src/data-original."),
    ])
    hidden_values = {
        "crawl_mode": crawl_mode,
        "listing_item_selector": listing,
        "detail_link_selector": detail_link,
        "detail_url_contains": detail_contains,
        "max_detail_pages": max_pages,
        "sample_detail_url": sample_detail,
        **mapped,
    }
    hidden = ''.join(f'<input type="hidden" name="{name}" value="{_safe(val)}">' for name, val in hidden_values.items())
    save = ""
    if preview_items:
        save = f'''<form method="post" action="/sources-registry/{source_id}/mapping/save" class="row" style="margin-top:14px">{hidden}<button class="btn good">Сохранить схему</button><span class="muted">После сохранения сайт включится и будет собираться только по этой схеме.</span></form>'''

    body = f'''{flash}{err}
    <div class="card"><h2>Одноразовая настройка: {_safe(snapshot['name'], 'Источник')}</h2><div class="muted">{_safe(snapshot['url'])}</div><p>Номер строки HTML не используем: он меняется. Используем selectors элементов, скопированные через «Исследовать элемент → Copy → Copy selector».</p></div>
    <form method="post" action="/sources-registry/{source_id}/mapping/preview">
      <div class="card"><h2>1. Как устроен источник</h2>
        <div class="field"><label>Режим</label><select name="crawl_mode"><option value="direct"{direct_selected}>На этой странице уже лежат предложения</option><option value="follow_internal"{follow_selected}>Каталог → открыть внутреннюю страницу каждого сервиса</option></select></div>
        <div class="muted">Для Promokood категории вроде /travel подходит второй режим: парсер находит внутреннюю кнопку «Все промокоды», переходит только на страницы того же домена (например /o/...), а внешние «Активировать» для обхода игнорирует.</div>
        {_field('Карточка сервиса в каталоге', 'listing_item_selector', listing, 'Нужна только для режима «Каталог». Copy selector одной карточки сервиса.')}
        {_field('Внутренняя кнопка/ссылка «Все промокоды»', 'detail_link_selector', detail_link, 'Нужна только для режима «Каталог». Selector ссылки внутри карточки.')}
        {_field('Фильтр внутренних адресов', 'detail_url_contains', detail_contains, 'Например /o/. Это дополнительно защищает от перехода на рекламодателя.', '/o/')}
        {_field('Пример внутренней страницы (необязательно)', 'sample_detail_url', sample_detail, 'Можно вставить известную страницу вроде https://promokood.ru/o/vseinstrumenti. Если пусто, для проверки будет взята первая найденная внутренняя ссылка.')}
        <div class="field"><label>Максимум внутренних страниц за запуск</label><input type="number" min="1" max="500" name="max_detail_pages" value="{_safe(max_pages or '100')}"></div>
      </div>
      <div class="card"><h2>2. Что брать со страницы-шаблона и в какую графу</h2>{form_fields}<div class="row"><button class="btn good">Проверить схему</button><a class="btn secondary" href="/sources-registry">Отмена</a></div></div>
    </form>
    {_preview(preview_items, detail_page_url=detail_page_url, discovered_urls=discovered_urls or []) if preview_items else ''}
    {save}'''
    return _layout("Настройка сайта", body)


def mapping_preview_v2(
    source_id: int,
    crawl_mode: str = Form("direct"), listing_item_selector: str = Form(""), detail_link_selector: str = Form(""),
    detail_url_contains: str = Form(""), max_detail_pages: int = Form(100), sample_detail_url: str = Form(""),
    item_selector: str = Form(...), title_selector: str = Form(""), promo_code_selector: str = Form(""),
    promo_code_attribute: str = Form(""), conditions_selector: str = Form(""), valid_until_selector: str = Form(""),
    link_selector: str = Form(""), image_selector: str = Form(""), image_attribute: str = Form(""),
):
    values = {name: str(value) for name, value in locals().copy().items() if name not in {"source_id"}}
    snapshot = _source_snapshot(source_id)
    if snapshot is None:
        return HTMLResponse("Source not found", status_code=404)
    try:
        follow = _mode_profile(crawl_mode=crawl_mode, listing_item_selector=listing_item_selector, detail_link_selector=detail_link_selector, detail_url_contains=detail_url_contains, max_detail_pages=max_detail_pages)
        profile = normalize_manual_profile(item_selector=item_selector, title_selector=title_selector, promo_code_selector=promo_code_selector, promo_code_attribute=promo_code_attribute, conditions_selector=conditions_selector, valid_until_selector=valid_until_selector, link_selector=link_selector, image_selector=image_selector, image_attribute=image_attribute)
        collector = GenericWebCollector()
        page_url, html_text, discovered = _resolve_preview_page(collector, snapshot, follow, sample_detail_url)
        items = preview_manual_profile_html(html_text, page_url=page_url, profile=profile, limit=5)
        if not items or not any(item.title or item.conditions or item.promo_code for item in items):
            raise ValueError("Страница найдена, но выбранные поля пустые.")
        values.update({
            "item_selector": profile.item_selector,
            "title_selector": profile.title_selector or "",
            "promo_code_selector": profile.promo_code_selector or "",
            "promo_code_attribute": profile.promo_code_attribute or "",
            "conditions_selector": profile.conditions_selector or "",
            "valid_until_selector": profile.valid_until_selector or "",
            "link_selector": profile.link_selector or "",
            "image_selector": profile.image_selector or "",
            "image_attribute": profile.image_attribute or "",
            "listing_item_selector": follow.listing_item_selector or "",
            "detail_link_selector": follow.detail_link_selector or "",
            "detail_url_contains": follow.detail_url_contains or "",
            "max_detail_pages": str(follow.max_detail_pages),
            "sample_detail_url": page_url if follow.crawl_mode == "follow_internal" else sample_detail_url,
        })
        return mapping_page_v2(source_id, values=values, preview_items=items, detail_page_url=page_url, discovered_urls=discovered, message="Схема работает. Проверьте значения по графам и сохраните.")
    except Exception as exc:
        return mapping_page_v2(source_id, values=values, error=f"Не удалось проверить схему: {type(exc).__name__}: {exc}")


def mapping_save_v2(
    source_id: int,
    crawl_mode: str = Form("direct"), listing_item_selector: str = Form(""), detail_link_selector: str = Form(""),
    detail_url_contains: str = Form(""), max_detail_pages: int = Form(100), sample_detail_url: str = Form(""),
    item_selector: str = Form(...), title_selector: str = Form(""), promo_code_selector: str = Form(""),
    promo_code_attribute: str = Form(""), conditions_selector: str = Form(""), valid_until_selector: str = Form(""),
    link_selector: str = Form(""), image_selector: str = Form(""), image_attribute: str = Form(""),
):
    values = {name: str(value) for name, value in locals().copy().items() if name not in {"source_id"}}
    snapshot = _source_snapshot(source_id)
    if snapshot is None:
        return HTMLResponse("Source not found", status_code=404)
    try:
        follow = _mode_profile(crawl_mode=crawl_mode, listing_item_selector=listing_item_selector, detail_link_selector=detail_link_selector, detail_url_contains=detail_url_contains, max_detail_pages=max_detail_pages)
        profile = normalize_manual_profile(item_selector=item_selector, title_selector=title_selector, promo_code_selector=promo_code_selector, promo_code_attribute=promo_code_attribute, conditions_selector=conditions_selector, valid_until_selector=valid_until_selector, link_selector=link_selector, image_selector=image_selector, image_attribute=image_attribute)
        collector = GenericWebCollector()
        page_url, html_text, _ = _resolve_preview_page(collector, snapshot, follow, sample_detail_url)
        items = preview_manual_profile_html(html_text, page_url=page_url, profile=profile, limit=3)
        if not items or not any(item.title or item.conditions or item.promo_code for item in items):
            raise ValueError("Контрольная проверка схемы не прошла.")
        with session_scope() as session:
            update_source(session, source_id, collector_type="generic_web", item_selector=profile.item_selector, title_selector=profile.title_selector, promo_code_selector=profile.promo_code_selector, promo_code_attribute=profile.promo_code_attribute, conditions_selector=profile.conditions_selector, valid_until_selector=profile.valid_until_selector, link_selector=profile.link_selector)
            set_source_enabled(session, source_id, True)
        set_image_profile(source_id, image_selector=profile.image_selector, image_attribute=profile.image_attribute)
        set_follow_profile(source_id, crawl_mode=follow.crawl_mode, listing_item_selector=follow.listing_item_selector, detail_link_selector=follow.detail_link_selector, detail_url_contains=follow.detail_url_contains, max_detail_pages=follow.max_detail_pages)
    except Exception as exc:
        return mapping_page_v2(source_id, values=values, error=f"Схема не сохранена: {type(exc).__name__}: {exc}")
    return RedirectResponse(f'/sources-registry/{source_id}/mapping?message=' + quote('Схема сохранена. Источник включён и будет собираться по ней.'), status_code=303)


def _replace_route(app: FastAPI, path: str, method: str, endpoint) -> None:
    target = method.upper()
    app.router.routes[:] = [
        route for route in app.router.routes
        if not (getattr(route, "path", None) == path and target in set(getattr(route, "methods", set()) or set()))
    ]
    app.add_api_route(path, endpoint, methods=[target], response_class=HTMLResponse if target == "GET" else None)


def install_manual_mapping_v2(app: FastAPI) -> None:
    _replace_route(app, "/sources-registry/{source_id}/mapping", "GET", mapping_page_v2)
    _replace_route(app, "/sources-registry/{source_id}/mapping/preview", "POST", mapping_preview_v2)
    _replace_route(app, "/sources-registry/{source_id}/mapping/save", "POST", mapping_save_v2)
