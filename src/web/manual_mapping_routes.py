from __future__ import annotations

import html
from urllib.parse import quote

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from src.modules.source_registry.auto_setup import AutoSourceSetupError, analyze_source_url, normalize_source_url
from src.modules.source_registry.collectors import GenericWebCollector
from src.modules.source_registry.image_profiles import get_image_profile, set_image_profile
from src.modules.source_registry.manual_profile import ManualProfile, normalize_manual_profile, preview_manual_profile_html
from src.modules.source_registry.models import RegisteredSource
from src.modules.source_registry.service import create_source, set_source_enabled, update_source
from src.shared.db import create_session, session_scope
from src.web.setup import is_setup_complete
from src.web.source_registry_routes import _layout


router = APIRouter()


def _safe(value: object, fallback: str = "") -> str:
    raw = str(value).strip() if value is not None else ""
    return html.escape(raw or fallback, quote=True)


def _require_setup():
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    return None


def _source_snapshot(source_id: int) -> dict[str, object] | None:
    with create_session() as session:
        source = session.get(RegisteredSource, source_id)
        if source is None:
            return None
        image_selector, image_attribute = get_image_profile(source_id)
        return {
            "id": int(source.id),
            "name": source.name,
            "url": source.url,
            "platform": source.platform,
            "collector_type": source.collector_type,
            "network_policy": source.network_policy,
            "item_selector": source.item_selector,
            "title_selector": source.title_selector,
            "promo_code_selector": source.promo_code_selector,
            "promo_code_attribute": source.promo_code_attribute,
            "conditions_selector": source.conditions_selector,
            "valid_until_selector": source.valid_until_selector,
            "link_selector": source.link_selector,
            "image_selector": image_selector,
            "image_attribute": image_attribute,
        }


def _mapping_values(snapshot: dict[str, object], values: dict[str, str] | None = None) -> dict[str, str]:
    values = values or {}
    names = (
        "item_selector",
        "title_selector",
        "promo_code_selector",
        "promo_code_attribute",
        "conditions_selector",
        "valid_until_selector",
        "link_selector",
        "image_selector",
        "image_attribute",
    )
    return {name: values.get(name, str(snapshot.get(name) or "")) for name in names}


def _profile_from_values(values: dict[str, str]) -> ManualProfile:
    return normalize_manual_profile(
        item_selector=values.get("item_selector", ""),
        title_selector=values.get("title_selector"),
        promo_code_selector=values.get("promo_code_selector"),
        promo_code_attribute=values.get("promo_code_attribute"),
        conditions_selector=values.get("conditions_selector"),
        valid_until_selector=values.get("valid_until_selector"),
        link_selector=values.get("link_selector"),
        image_selector=values.get("image_selector"),
        image_attribute=values.get("image_attribute"),
    )


def _field(label: str, name: str, value: str, help_text: str, *, placeholder: str = "") -> str:
    return f'''
    <div class="field" style="margin-bottom:14px">
      <label>{_safe(label)}</label>
      <input name="{_safe(name)}" value="{_safe(value)}" placeholder="{_safe(placeholder)}" style="font-family:ui-monospace,Consolas,monospace">
      <div class="muted" style="font-size:12px;margin-top:5px">{_safe(help_text)}</div>
    </div>'''


def _preview_table(items) -> str:
    if not items:
        return ""
    rows = []
    for index, item in enumerate(items, 1):
        image = f'<a target="_blank" rel="noopener" href="{_safe(item.image_url)}">есть</a>' if item.image_url else "—"
        link = f'<a target="_blank" rel="noopener" href="{_safe(item.link)}">открыть</a>' if item.link else "—"
        discount = f"{_safe(item.discount_percent)}%" if item.discount_percent else _safe(item.amount_hint, "—")
        rows.append(
            "<tr>"
            f"<td>{index}</td><td>{_safe(item.title, '—')}</td><td>{_safe(item.promo_code, '—')}</td>"
            f"<td>{discount}</td><td>{_safe(item.conditions, '—')}</td><td>{_safe(item.valid_until, '—')}</td>"
            f"<td>{link}</td><td>{image}</td></tr>"
        )
    return f'''
    <div class="card">
      <h2>Предпросмотр настройки</h2>
      <div class="muted">Это именно те значения, которые выбранные элементы страницы дают парсеру. Если столбец неверный — вернитесь к странице сайта, выберите правильный элемент через «Исследовать элемент» и вставьте другой selector.</div>
      <div class="scroll" style="margin-top:12px"><table class="table"><thead><tr><th>#</th><th>Название</th><th>Промокод</th><th>Скидка</th><th>Условия</th><th>Срок</th><th>Ссылка</th><th>Фото</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    </div>'''


def _mapping_page(
    source_id: int,
    *,
    values: dict[str, str] | None = None,
    preview_items=None,
    message: str | None = None,
    error: str | None = None,
):
    redirect = _require_setup()
    if redirect:
        return redirect
    snapshot = _source_snapshot(source_id)
    if snapshot is None:
        return HTMLResponse("Source not found", status_code=404)
    form_values = _mapping_values(snapshot, values)
    flash = f'<div class="flash">{_safe(message)}</div>' if message else ""
    err = f'<div class="err">{_safe(error)}</div>' if error else ""

    fields = "".join(
        [
            _field(
                "1. Карточка одного предложения",
                "item_selector",
                form_values["item_selector"],
                "На сайте выберите целую карточку одного промокода/акции: Исследовать элемент → Copy → Copy selector. Номер строки не нужен и использовать его нельзя — строки меняются при каждом обновлении страницы.",
                placeholder="#app > main > div.offers > article:nth-child(1)",
            ),
            _field("2. Название предложения → графа «Название»", "title_selector", form_values["title_selector"], "Copy selector именно у текста названия внутри той же карточки."),
            _field("3. Промокод → графа «Промокод»", "promo_code_selector", form_values["promo_code_selector"], "Copy selector элемента, где находится сам код. Если код хранится не текстом, атрибут можно указать ниже."),
            _field("Атрибут промокода (обычно пусто)", "promo_code_attribute", form_values["promo_code_attribute"], "Например data-code, data-coupon или value. Если код виден обычным текстом — оставить пустым."),
            _field("4. Условия/описание → графа «Условия»", "conditions_selector", form_values["conditions_selector"], "Элемент с условиями акции. Из этого текста также определяются процент/сумма скидки, если они написаны на странице."),
            _field("5. Срок действия → графа «Действует до»", "valid_until_selector", form_values["valid_until_selector"], "Элемент с датой или фразой вида «до 31.08.2026»."),
            _field("6. Ссылка предложения → графа «Ссылка»", "link_selector", form_values["link_selector"], "Copy selector ссылки/кнопки внутри карточки. Парсер возьмёт href автоматически."),
            _field("7. Изображение → графа «Фото»", "image_selector", form_values["image_selector"], "Copy selector изображения внутри карточки."),
            _field("Атрибут изображения (обычно пусто)", "image_attribute", form_values["image_attribute"], "Обычно парсер сам проверяет src/data-src. Для нестандартного сайта можно указать data-original, data-src и т.п."),
        ]
    )

    hidden = "".join(
        f'<input type="hidden" name="{name}" value="{_safe(value)}">'
        for name, value in form_values.items()
    )
    save_controls = ""
    if preview_items:
        save_controls = f'''
        <form method="post" action="/sources-registry/{source_id}/mapping/save" class="row" style="margin-top:14px">
          {hidden}
          <button class="btn good">Сохранить эту схему для сайта</button>
          <span class="muted">После сохранения эта схема используется автоматически при каждом следующем сборе.</span>
        </form>'''

    body = f'''{flash}{err}
    <div class="card">
      <h2>Одноразовая настройка сайта: {_safe(snapshot['name'], 'Источник')}</h2>
      <div class="muted">{_safe(snapshot['url'])}</div>
      <p><b>Логика:</b> один раз показываем парсеру, где на этом сайте находится каждое поле. Потом он всегда собирает новые предложения по этой же схеме.</p>
      <p><b>Как получить selector:</b> откройте любое предложение на сайте → правой кнопкой по нужному элементу → «Исследовать элемент» → в DevTools правой кнопкой по выделенному HTML → Copy → Copy selector → вставьте сюда.</p>
      <p class="muted">Можно копировать selector конкретной первой/второй карточки: Discount Parser автоматически убирает конечный nth-child и превращает его в повторяемую схему, а selectors полей по возможности делает относительными к карточке.</p>
      <a class="btn secondary" target="_blank" rel="noopener" href="{_safe(snapshot['url'])}">Открыть сайт рядом</a>
    </div>
    <form method="post" action="/sources-registry/{source_id}/mapping/preview">
      <div class="card"><h2>Что откуда брать</h2>{fields}<div class="row"><button class="btn good">Проверить на странице</button><a class="btn secondary" href="/sources-registry">Отмена</a></div></div>
    </form>
    {_preview_table(preview_items)}
    {save_controls}
    <details class="card"><summary style="cursor:pointer;font-weight:700">Технические настройки для разработчика</summary>
      <div class="muted" style="margin:12px 0">Старую форму с collector/trust/network/reveal оставляем как аварийный инструмент, но для обычной настройки сайта она не нужна.</div>
      <a class="btn secondary" href="/sources-registry/{source_id}/edit">Открыть техническую форму</a>
    </details>'''
    return _layout("Настройка полей сайта", body)


@router.get('/sources-registry/{source_id}/mapping', response_class=HTMLResponse)
def source_mapping_page(source_id: int, message: str | None = None, error: str | None = None):
    return _mapping_page(source_id, message=message, error=error)


@router.post('/sources-registry/{source_id}/mapping/preview', response_class=HTMLResponse)
def source_mapping_preview(
    source_id: int,
    item_selector: str = Form(...),
    title_selector: str = Form(''),
    promo_code_selector: str = Form(''),
    promo_code_attribute: str = Form(''),
    conditions_selector: str = Form(''),
    valid_until_selector: str = Form(''),
    link_selector: str = Form(''),
    image_selector: str = Form(''),
    image_attribute: str = Form(''),
):
    values = {
        "item_selector": item_selector,
        "title_selector": title_selector,
        "promo_code_selector": promo_code_selector,
        "promo_code_attribute": promo_code_attribute,
        "conditions_selector": conditions_selector,
        "valid_until_selector": valid_until_selector,
        "link_selector": link_selector,
        "image_selector": image_selector,
        "image_attribute": image_attribute,
    }
    snapshot = _source_snapshot(source_id)
    if snapshot is None:
        return HTMLResponse("Source not found", status_code=404)
    try:
        profile = _profile_from_values(values)
        collector = GenericWebCollector()
        response = collector._get(str(snapshot["url"]), route=str(snapshot["network_policy"] or "auto"))
        preview = preview_manual_profile_html(response.text, page_url=str(response.url), profile=profile, limit=5)
        if not any(item.title or item.conditions or item.promo_code for item in preview):
            raise ValueError("Карточки найдены, но выбранные поля пустые. Проверьте selectors полей.")
        normalized_values = {
            "item_selector": profile.item_selector,
            "title_selector": profile.title_selector or "",
            "promo_code_selector": profile.promo_code_selector or "",
            "promo_code_attribute": profile.promo_code_attribute or "",
            "conditions_selector": profile.conditions_selector or "",
            "valid_until_selector": profile.valid_until_selector or "",
            "link_selector": profile.link_selector or "",
            "image_selector": profile.image_selector or "",
            "image_attribute": profile.image_attribute or "",
        }
        return _mapping_page(source_id, values=normalized_values, preview_items=preview, message="Селекторы работают. Проверьте таблицу и сохраните схему.")
    except Exception as exc:
        return _mapping_page(source_id, values=values, error=f"Не удалось проверить настройку: {type(exc).__name__}: {exc}")


@router.post('/sources-registry/{source_id}/mapping/save')
def source_mapping_save(
    source_id: int,
    item_selector: str = Form(...),
    title_selector: str = Form(''),
    promo_code_selector: str = Form(''),
    promo_code_attribute: str = Form(''),
    conditions_selector: str = Form(''),
    valid_until_selector: str = Form(''),
    link_selector: str = Form(''),
    image_selector: str = Form(''),
    image_attribute: str = Form(''),
):
    values = {
        "item_selector": item_selector,
        "title_selector": title_selector,
        "promo_code_selector": promo_code_selector,
        "promo_code_attribute": promo_code_attribute,
        "conditions_selector": conditions_selector,
        "valid_until_selector": valid_until_selector,
        "link_selector": link_selector,
        "image_selector": image_selector,
        "image_attribute": image_attribute,
    }
    snapshot = _source_snapshot(source_id)
    if snapshot is None:
        return HTMLResponse("Source not found", status_code=404)
    try:
        profile = _profile_from_values(values)
        collector = GenericWebCollector()
        response = collector._get(str(snapshot["url"]), route=str(snapshot["network_policy"] or "auto"))
        preview = preview_manual_profile_html(response.text, page_url=str(response.url), profile=profile, limit=3)
        if not preview or not any(item.title or item.conditions or item.promo_code for item in preview):
            raise ValueError("Профиль не прошёл контрольную проверку и не сохранён.")
        with session_scope() as session:
            update_source(
                session,
                source_id,
                collector_type="generic_web",
                item_selector=profile.item_selector,
                title_selector=profile.title_selector,
                promo_code_selector=profile.promo_code_selector,
                promo_code_attribute=profile.promo_code_attribute,
                conditions_selector=profile.conditions_selector,
                valid_until_selector=profile.valid_until_selector,
                link_selector=profile.link_selector,
            )
            set_source_enabled(session, source_id, True)
        set_image_profile(source_id, image_selector=profile.image_selector, image_attribute=profile.image_attribute)
    except Exception as exc:
        return _mapping_page(source_id, values=values, error=f"Схема не сохранена: {type(exc).__name__}: {exc}")
    return RedirectResponse(
        f'/sources-registry/{source_id}/mapping?message=' + quote('Схема сохранена. Теперь этот сайт будет собираться по ней.'),
        status_code=303,
    )


@router.get('/sources-registry/{source_id}/settings', response_class=HTMLResponse)
def source_settings_page(source_id: int, error: str | None = None):
    redirect = _require_setup()
    if redirect:
        return redirect
    snapshot = _source_snapshot(source_id)
    if snapshot is None:
        return HTMLResponse("Source not found", status_code=404)
    err = f'<div class="err">{_safe(error)}</div>' if error else ""
    mapping_state = "Настроена" if snapshot.get("item_selector") else "Нужно настроить один раз"
    body = f'''{err}
    <div class="card">
      <h2>{_safe(snapshot['name'], 'Источник')}</h2>
      <form method="post" action="/sources-registry/{source_id}/settings" style="margin-top:16px">
        <div class="grid">
          <div class="field"><label>Название</label><input name="name" value="{_safe(snapshot['name'])}"></div>
          <div class="field"><label>Ссылка</label><input name="url" value="{_safe(snapshot['url'])}" required></div>
        </div>
        <div class="row" style="margin-top:16px"><button class="btn good">Сохранить</button><a class="btn secondary" href="/sources-registry">Отмена</a></div>
      </form>
    </div>
    <div class="card">
      <h2>Схема сбора с сайта</h2><div class="muted">Состояние: {_safe(mapping_state)}</div>
      <p>Для сайта один раз укажите, какой элемент страницы соответствует названию, промокоду, условиям, сроку, ссылке и фото. После этого новые предложения будут собираться по той же схеме.</p>
      <a class="btn good" href="/sources-registry/{source_id}/mapping">Настроить поля сайта</a>
    </div>
    <details class="card"><summary style="cursor:pointer;font-weight:700">Для разработчика</summary>
      <div class="muted" style="margin:12px 0">Collector, trust, network и reveal-настройки.</div>
      <a class="btn secondary" href="/sources-registry/{source_id}/edit">Открыть техническую форму</a>
    </details>'''
    return _layout("Изменить источник", body)


@router.post('/sources-registry/{source_id}/settings')
def source_settings_save(source_id: int, name: str = Form(''), url: str = Form(...)):
    try:
        normalized = normalize_source_url(url)
        with create_session() as session:
            current = session.get(RegisteredSource, source_id)
            if current is None:
                return HTMLResponse("Source not found", status_code=404)
            old_url = current.url
        values: dict[str, object] = {"url": normalized}
        if name.strip():
            values["name"] = name.strip()
        changed_url = normalized != old_url
        if changed_url:
            analysis = analyze_source_url(normalized)
            if not analysis.can_add:
                raise AutoSourceSetupError("Новая ссылка не прошла проверку.")
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
            updated = update_source(session, source_id, **values)
            if changed_url and updated.platform == "website":
                set_source_enabled(session, source_id, False)
        if changed_url:
            set_image_profile(source_id, image_selector=None, image_attribute=None)
    except Exception as exc:
        message = str(exc) if isinstance(exc, AutoSourceSetupError) else f'{type(exc).__name__}: {exc}'
        return RedirectResponse(f'/sources-registry/{source_id}/settings?error=' + quote(message), status_code=303)
    if changed_url:
        return RedirectResponse(f'/sources-registry/{source_id}/mapping?message=' + quote('Ссылка изменена. Один раз настройте поля для новой страницы.'), status_code=303)
    return RedirectResponse('/sources-registry?message=' + quote('Источник обновлён'), status_code=303)


@router.post('/sources-registry/add-auto')
def add_auto_source_route(url: str = Form(...)):
    redirect = _require_setup()
    if redirect:
        return redirect
    try:
        analysis = analyze_source_url(url)
        if not analysis.can_add:
            raise AutoSourceSetupError("На странице не удалось найти предложения.")
        with session_scope() as session:
            existing = session.scalar(select(RegisteredSource).where(RegisteredSource.url == analysis.url))
            if existing is None:
                source = create_source(
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
                    enabled=analysis.platform != "website",
                )
            else:
                source = existing
            source_id = int(source.id)
            platform = source.platform
    except Exception as exc:
        message = str(exc) if isinstance(exc, AutoSourceSetupError) else f'{type(exc).__name__}: {exc}'
        return RedirectResponse('/sources-registry?error=' + quote(message), status_code=303)
    if platform == "website":
        return RedirectResponse(
            f'/sources-registry/{source_id}/mapping?message=' + quote('Источник добавлен. Теперь один раз укажите, где на этом сайте находятся нужные поля.'),
            status_code=303,
        )
    return RedirectResponse('/sources-registry?message=' + quote('Источник добавлен и готов к сбору'), status_code=303)
