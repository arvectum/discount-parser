from __future__ import annotations

import asyncio
import html
import logging
from urllib.parse import quote

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, text

from src.modules.source_registry.image_profiles import (
    get_image_profile,
    install_profile_image_extraction,
    set_image_profile,
)
from src.modules.source_registry.models import RegisteredSource
from src.shared.config import get_settings
from src.shared.db import create_session, session_scope
from src.shared.logging import redact_secrets
from src.telegram.client import build_bot
from src.telegram.publisher import PublishResult, publish_offer

logger = logging.getLogger(__name__)


def _clean_error(value: str | None) -> str:
    if not value:
        return "неизвестная ошибка Telegram"
    clean = redact_secrets(value).replace("\r", " ").replace("\n", " ").strip()
    if len(clean) > 260:
        clean = clean[:257] + "..."
    return clean


def _result_message(result: PublishResult) -> str:
    if result.status == "published":
        return "Публикация выполнена."
    if result.status == "duplicate":
        return "Это предложение уже зарезервировано или опубликовано."
    if result.status == "not_publishable":
        return "Предложение сейчас недоступно для публикации."
    if result.status == "not_found":
        return "Предложение не найдено."
    if result.status == "failed":
        return f"Публикация не выполнена: {_clean_error(result.error)}. Предложение осталось в очереди, отправку можно повторить."
    return f"Публикация завершилась со статусом: {result.status}."


def web_publish_hotfix(offer_id: int):
    """Manual publish path that uses the same network router as autoposting."""
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_channel_id:
        return RedirectResponse('/setup', status_code=303)

    async def _publish() -> PublishResult:
        bot = build_bot(settings.telegram_bot_token)
        try:
            return await publish_offer(
                bot,
                offer_id=offer_id,
                channel_id=settings.telegram_channel_id,
            )
        finally:
            await bot.session.close()

    try:
        result = asyncio.run(_publish())
    except Exception as exc:
        clean = _clean_error(f"{type(exc).__name__}: {exc}")
        logger.warning("manual_publish_route_failed offer_id=%s error=%s", offer_id, clean)
        message = f"Публикация не выполнена: {clean}. Предложение осталось в очереди, отправку можно повторить."
        return RedirectResponse('/?message=' + quote(message, safe=''), status_code=303)

    if result.status == "failed":
        logger.warning(
            "manual_publish_failed offer_id=%s publication_id=%s error=%s",
            offer_id,
            result.publication_id,
            _clean_error(result.error),
        )
    return RedirectResponse('/?message=' + quote(_result_message(result), safe=''), status_code=303)


def _repair_registry_rows_runtime() -> None:
    """Make the source screen tolerant of legacy/customer DB rows on every upgrade.

    Customer evidence showed that some upgraded databases still contain NULLs
    in source-registry rows even after the historical migration path.  Normalize
    all three UI-backed tables immediately before rendering, then keep the safe
    fallback as a final guard so malformed legacy data cannot become HTTP 500.
    """
    with session_scope() as session:
        session.execute(
            text(
                """
                UPDATE registered_sources
                SET
                    key = COALESCE(NULLIF(key, ''), 'legacy-source-' || id),
                    name = COALESCE(NULLIF(name, ''), NULLIF(key, ''), 'Источник #' || id),
                    platform = CASE
                        WHEN platform IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other') THEN platform
                        ELSE 'other'
                    END,
                    source_type = COALESCE(NULLIF(source_type, ''), 'other'),
                    url = COALESCE(url, ''),
                    collector_type = COALESCE(NULLIF(collector_type, ''), 'legacy_adapter'),
                    network_policy = CASE
                        WHEN network_policy IN ('auto','direct','proxy','system') THEN network_policy
                        ELSE 'auto'
                    END,
                    priority = COALESCE(priority, 50),
                    trust_level = CASE
                        WHEN trust_level IN ('official','verified','community','aggregator','unknown') THEN trust_level
                        ELSE 'unknown'
                    END,
                    check_interval_minutes = CASE
                        WHEN check_interval_minutes IS NULL OR check_interval_minutes < 1 THEN 120
                        ELSE check_interval_minutes
                    END,
                    enabled = COALESCE(enabled, 0),
                    status = CASE
                        WHEN status IN ('healthy','degraded','blocked','requires_credentials','disabled','unknown') THEN status
                        ELSE 'unknown'
                    END,
                    failure_count = COALESCE(failure_count, 0)
                WHERE
                    key IS NULL OR key = '' OR name IS NULL OR name = '' OR
                    platform IS NULL OR platform NOT IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other') OR
                    source_type IS NULL OR source_type = '' OR url IS NULL OR
                    collector_type IS NULL OR collector_type = '' OR
                    network_policy IS NULL OR network_policy NOT IN ('auto','direct','proxy','system') OR
                    priority IS NULL OR trust_level IS NULL OR
                    trust_level NOT IN ('official','verified','community','aggregator','unknown') OR
                    check_interval_minutes IS NULL OR check_interval_minutes < 1 OR
                    enabled IS NULL OR status IS NULL OR
                    status NOT IN ('healthy','degraded','blocked','requires_credentials','disabled','unknown') OR
                    failure_count IS NULL
                """
            )
        )
        session.execute(
            text(
                """
                UPDATE source_candidates
                SET
                    platform = CASE
                        WHEN platform IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other') THEN platform
                        ELSE 'other'
                    END,
                    url = COALESCE(url, ''),
                    discovered_by = COALESCE(NULLIF(discovered_by, ''), 'legacy'),
                    status = CASE
                        WHEN status IN ('new','approved','rejected','ignored','invalid') THEN status
                        ELSE 'new'
                    END,
                    confidence = COALESCE(confidence, 0.0)
                WHERE
                    platform IS NULL OR platform NOT IN ('website','promo_aggregator','telegram','vk','dzen','rutube','other') OR
                    url IS NULL OR discovered_by IS NULL OR discovered_by = '' OR
                    status IS NULL OR status NOT IN ('new','approved','rejected','ignored','invalid') OR
                    confidence IS NULL
                """
            )
        )
        session.execute(
            text(
                """
                UPDATE source_keywords
                SET
                    keyword = COALESCE(NULLIF(keyword, ''), 'legacy-keyword-' || id),
                    normalized_keyword = COALESCE(NULLIF(normalized_keyword, ''), 'legacy-keyword-' || id),
                    kind = CASE
                        WHEN kind IN ('strong_positive','positive','negative','merchant','promo_code','price','custom') THEN kind
                        ELSE 'custom'
                    END,
                    enabled = COALESCE(enabled, 0),
                    priority = COALESCE(priority, 50)
                WHERE
                    keyword IS NULL OR keyword = '' OR normalized_keyword IS NULL OR normalized_keyword = '' OR
                    kind IS NULL OR kind NOT IN ('strong_positive','positive','negative','merchant','promo_code','price','custom') OR
                    enabled IS NULL OR priority IS NULL
                """
            )
        )


def _safe(value: object, fallback: str = "—") -> str:
    raw = str(value).strip() if value is not None else ""
    return html.escape(raw or fallback, quote=True)


def _fallback_registry_page(*, message: str | None, error: str | None, failure: Exception) -> HTMLResponse:
    with create_session() as session:
        rows = session.scalars(select(RegisteredSource).order_by(RegisteredSource.id)).all()
        snapshots = [
            {
                "id": row.id,
                "name": row.name,
                "key": row.key,
                "platform": row.platform,
                "source_type": row.source_type,
                "merchant": row.merchant,
                "url": row.url,
                "collector_type": row.collector_type,
                "enabled": row.enabled,
                "status": row.status,
                "last_error": row.last_error,
            }
            for row in rows
        ]

    table_rows: list[str] = []
    for row in snapshots:
        raw_url = str(row["url"] or "").strip()
        url_cell = _safe(raw_url)
        if raw_url.startswith(("http://", "https://")):
            escaped_url = html.escape(raw_url, quote=True)
            url_cell = f'<a href="{escaped_url}" target="_blank" rel="noopener">открыть</a>'
        enabled = "ВКЛ" if row["enabled"] else "ВЫКЛ"
        table_rows.append(
            "<tr>"
            f"<td><b>{_safe(row['name'])}</b><br><span class='muted'>{_safe(row['key'])}</span></td>"
            f"<td>{_safe(row['platform'])}<br><span class='muted'>{_safe(row['source_type'])}</span></td>"
            f"<td>{_safe(row['merchant'])}</td>"
            f"<td>{url_cell}<br><span class='muted'>{_safe(row['collector_type'])}</span></td>"
            f"<td>{enabled}<br>{_safe(row['status'])}</td>"
            f"<td>{_safe(str(row['last_error'] or '')[:180])}</td>"
            f"<td><a class='btn' href='/sources-registry/{int(row['id'])}/edit'>Настроить поля</a></td>"
            "</tr>"
        )

    flash = f"<div class='flash'>{_safe(message)}</div>" if message else ""
    customer_error = f"<div class='err'>{_safe(error)}</div>" if error else ""
    diagnostic = _safe(f"{type(failure).__name__}: {failure}")
    body = f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Источники</title><style>
    :root{{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#18212f;background:#f5f7fb}}
    *{{box-sizing:border-box}}body{{margin:0}}.wrap{{max-width:1280px;margin:auto;padding:28px}}.nav{{display:flex;gap:9px;flex-wrap:wrap}}.nav a,.btn{{display:inline-block;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:650;background:#e8edf4;color:#334155}}.card{{background:#fff;border:1px solid #e5e7eb;border-radius:15px;padding:18px;margin-top:18px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:9px;border-bottom:1px solid #e5e7eb;vertical-align:top}}.muted{{color:#64748b}}.flash{{padding:12px;border-radius:10px;background:#dcfce7;color:#166534;margin-top:16px}}.err{{padding:12px;border-radius:10px;background:#fee2e2;color:#991b1b;margin-top:16px}}.warn{{padding:12px;border-radius:10px;background:#fef3c7;color:#92400e;margin-top:16px}}.scroll{{overflow:auto}}
    </style></head><body><div class='wrap'><h1>Источники</h1><div class='nav'><a href='/'>Главная</a><a href='/sources-registry'>Источники</a><a href='/offers'>Предложения</a><a href='/runs'>Журнал</a><a href='/system'>Система</a></div>{flash}{customer_error}
    <div class='warn'>Основной экран источников был автоматически переведён в безопасный режим. Данные сохранены; источники можно открывать и настраивать. Диагностика: {diagnostic}</div>
    <div class='card'><div class='scroll'><table><thead><tr><th>Источник</th><th>Платформа</th><th>Магазин</th><th>URL / collector</th><th>Состояние</th><th>Последняя ошибка</th><th>Действия</th></tr></thead><tbody>{''.join(table_rows) or '<tr><td colspan="7">Источников пока нет.</td></tr>'}</tbody></table></div></div></div></body></html>"""
    return HTMLResponse(body)


def sources_registry_hotfix(message: str | None = None, error: str | None = None):
    """Render Sources without allowing one legacy row to take down the panel."""
    try:
        _repair_registry_rows_runtime()
        from src.web import source_registry_routes

        return source_registry_routes.registry_page(message=message, error=error)
    except Exception as exc:
        logger.exception("sources_registry_render_failed_using_safe_fallback")
        try:
            return _fallback_registry_page(message=message, error=error, failure=exc)
        except Exception as fallback_exc:
            logger.exception("sources_registry_safe_fallback_failed")
            clean = _safe(f"{type(fallback_exc).__name__}: {fallback_exc}")
            return HTMLResponse(
                "<!doctype html><html lang='ru'><meta charset='utf-8'><body>"
                "<h1>Источники</h1><p>Не удалось прочитать реестр источников.</p>"
                f"<pre>{clean}</pre><p><a href='/system'>Открыть диагностику системы</a></p></body></html>",
                status_code=200,
            )


def image_profile_save(
    source_id: int,
    image_selector: str = Form(""),
    image_attribute: str = Form(""),
):
    try:
        with create_session() as session:
            if session.get(RegisteredSource, source_id) is None:
                return HTMLResponse("Source not found", status_code=404)
        set_image_profile(
            source_id,
            image_selector=image_selector or None,
            image_attribute=image_attribute or None,
        )
    except Exception as exc:
        return RedirectResponse(
            f"/sources-registry/{source_id}/edit?error=" + quote(f"{type(exc).__name__}: {exc}"),
            status_code=303,
        )
    return RedirectResponse(
        f"/sources-registry/{source_id}/edit?message=" + quote("Настройки изображения сохранены"),
        status_code=303,
    )


def _install_image_profile_form_patch() -> None:
    from src.web import source_registry_routes

    original = source_registry_routes._source_edit_form
    if getattr(original, "_dp_fb5_image_profile_form", False):
        return

    def _source_edit_form_with_image(source: RegisteredSource) -> str:
        base = original(source)
        selector, attribute = get_image_profile(source.id)
        selector_value = html.escape(selector or "", quote=True)
        attribute_value = html.escape(attribute or "", quote=True)
        card = f"""
        <div class="card">
          <h2>Картинка предложения</h2>
          <div class="muted">Необязательно. Если CSS-селектор пустой, парсер автоматически возьмёт первую подходящую картинку внутри контейнера предложения. Для lazy-load можно указать атрибут <code>data-src</code>, <code>data-original</code> или другой атрибут сайта. При недоступной картинке Telegram автоматически опубликует обычный текстовый пост.</div>
          <form method="post" action="/sources-registry/{source.id}/image-profile" style="margin-top:16px">
            <div class="grid">
              <div class="field"><label>CSS-селектор картинки</label><input name="image_selector" value="{selector_value}" placeholder="img.offer-image, picture img"></div>
              <div class="field"><label>Атрибут картинки</label><input name="image_attribute" value="{attribute_value}" placeholder="src / data-src / data-original"></div>
            </div>
            <button class="btn good" style="margin-top:12px">Сохранить картинку</button>
          </form>
        </div>"""
        return base + card

    setattr(_source_edit_form_with_image, "_dp_fb5_image_profile_form", True)
    source_registry_routes._source_edit_form = _source_edit_form_with_image


def _replace_route(app: FastAPI, path: str, method: str, endpoint) -> None:
    target_method = method.upper()
    retained = []
    for route in app.router.routes:
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", None) == path and target_method in methods:
            continue
        retained.append(route)
    app.router.routes[:] = retained
    app.add_api_route(path, endpoint, methods=[target_method])


def install_customer_hotfixes(app: FastAPI) -> None:
    """Install customer-facing upgrade-safe route and extraction replacements."""
    install_profile_image_extraction()
    _install_image_profile_form_patch()
    _replace_route(app, "/publish/{offer_id}", "POST", web_publish_hotfix)
    _replace_route(app, "/sources-registry", "GET", sources_registry_hotfix)
    _replace_route(app, "/sources-registry/{source_id}/image-profile", "POST", image_profile_save)
