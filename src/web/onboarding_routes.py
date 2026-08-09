from __future__ import annotations

import html
import sys

import httpx
from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from src.qa.doctor import build_doctor_report
from src.shared.config import get_settings
from src.web.processes import process_manager
from src.web.setup import (
    is_setup_complete,
    save_telegram_collector_setup,
    save_telegram_setup,
    save_vk_setup,
)

router = APIRouter()

_STYLE = '''
<style>
:root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#18212f;background:#f5f7fb}
*{box-sizing:border-box}body{margin:0}.wizard{max-width:760px;margin:42px auto;padding:0 18px}.card{background:#fff;border:1px solid #e5e7eb;border-radius:18px;padding:28px;box-shadow:0 8px 28px rgba(15,23,42,.06)}
h1{margin:0 0 8px;font-size:28px}h2{margin:0 0 10px;font-size:21px}.muted{color:#64748b}.progress{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin:22px 0}.progress span{height:7px;border-radius:99px;background:#e5e7eb}.progress .done{background:#0f766e}.field{margin:17px 0}.field label{display:block;font-weight:650;margin-bottom:6px}.field input,.field select{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:9px;font-size:15px;background:#fff}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.btn{display:inline-block;border:0;border-radius:10px;padding:11px 15px;font-weight:650;cursor:pointer;text-decoration:none;background:#111827;color:#fff}.btn.good{background:#0f766e}.btn.secondary{background:#e5e7eb;color:#111827}.error{background:#fee2e2;color:#991b1b;padding:12px;border-radius:10px;margin:14px 0}.ok{background:#dcfce7;color:#166534;padding:12px;border-radius:10px;margin:14px 0}.warn{background:#fef3c7;color:#92400e;padding:12px;border-radius:10px;margin:14px 0}.choice{display:block;border:1px solid #e5e7eb;border-radius:12px;padding:14px;margin:10px 0}.check{padding:10px 0;border-bottom:1px solid #eef2f7}.check:last-child{border-bottom:0}.status{font-weight:700}.goodtext{color:#166534}.badtext{color:#991b1b}.optional{color:#92400e}.secret-note{font-size:13px;color:#64748b;margin-top:5px}
</style>
'''


def _page(step: int, title: str, body: str) -> HTMLResponse:
    progress = ''.join(f'<span class="{"done" if index <= step else ""}"></span>' for index in range(1, 6))
    return HTMLResponse(
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(title)} — Discount Parser</title>{_STYLE}</head><body>'
        f'<div class="wizard"><div class="card"><div class="muted">Настройка · шаг {step} из 5</div>'
        f'<div class="progress">{progress}</div>{body}</div></div></body></html>'
    )


def _error(message: str) -> str:
    return f'<div class="error">{html.escape(message)}</div>'


def _test_telegram(bot_token: str, channel_id: str) -> tuple[bool, str]:
    try:
        with httpx.Client(timeout=12.0) as client:
            me = client.get(f'https://api.telegram.org/bot{bot_token}/getMe')
            payload = me.json()
            if not me.is_success or not payload.get('ok'):
                return False, 'Telegram отклонил токен бота.'
            username = payload.get('result', {}).get('username') or 'bot'
            chat = client.get(
                f'https://api.telegram.org/bot{bot_token}/getChat',
                params={'chat_id': channel_id},
            )
            chat_payload = chat.json()
            if not chat.is_success or not chat_payload.get('ok'):
                return False, f'Бот @{username} найден, но канал недоступен. Проверьте ID/@username и права бота.'
        return True, f'Бот @{username} и канал доступны через Telegram Bot API.'
    except Exception as exc:
        return False, f'Не удалось проверить Telegram: {type(exc).__name__}. Проверьте интернет и повторите.'


def _test_vk(access_token: str, api_version: str) -> tuple[bool, str]:
    if not access_token.strip():
        return True, 'VK пропущен.'
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.get(
                'https://api.vk.com/method/users.get',
                params={'access_token': access_token, 'v': api_version},
            )
        payload = response.json()
        if 'error' in payload:
            code = payload['error'].get('error_code', '?')
            return False, f'VK API отклонил token (error {code}).'
        return True, 'VK API token принят.'
    except Exception as exc:
        return False, f'Не удалось проверить VK: {type(exc).__name__}. Проверьте интернет и повторите.'


@router.get('/onboarding', response_class=HTMLResponse)
def onboarding_start():
    return RedirectResponse('/onboarding/1', status_code=303)


@router.get('/onboarding/1', response_class=HTMLResponse)
def onboarding_telegram(error: str | None = None, checked: str | None = None):
    settings = get_settings()
    notice = _error(error) if error else (f'<div class="ok">{html.escape(checked)}</div>' if checked else '')
    body = f'''<h1>Telegram-бот</h1>
    <p class="muted">Бот управляет публикацией скидок и отправляет их в выбранный канал.</p>{notice}
    <form method="post" action="/onboarding/1">
      <div class="field"><label>Bot Token *</label><input type="password" name="bot_token" placeholder="123456789:AA..." required><div class="secret-note">Токен сохраняется локально в .env и не отображается после сохранения.</div></div>
      <div class="field"><label>Имя бота</label><input name="bot_name" value="{html.escape(settings.telegram_bot_name or '')}" placeholder="Discount Bot"></div>
      <div class="field"><label>Канал *</label><input name="channel_id" value="{html.escape(settings.telegram_channel_id or '')}" placeholder="@my_channel или -100..." required></div>
      <div class="field"><label>Ваш Telegram user ID *</label><input name="admin_ids" value="{html.escape(settings.telegram_admin_ids or '')}" placeholder="123456789" required></div>
      <div class="row"><button class="btn good" name="action" value="save">Сохранить и далее</button><button class="btn secondary" name="action" value="test">Проверить подключение</button></div>
    </form>'''
    return _page(1, 'Telegram-бот', body)


@router.post('/onboarding/1')
def onboarding_telegram_save(
    bot_token: str = Form(...),
    bot_name: str = Form(''),
    channel_id: str = Form(...),
    admin_ids: str = Form(...),
    action: str = Form('save'),
):
    try:
        save_telegram_setup(bot_token=bot_token, bot_name=bot_name, channel_id=channel_id, admin_ids=admin_ids)
    except ValueError as exc:
        return onboarding_telegram(error=str(exc))
    if action == 'test':
        ok, detail = _test_telegram(bot_token, channel_id)
        if not ok:
            return onboarding_telegram(error=detail)
        return onboarding_telegram(checked=detail)
    return RedirectResponse('/onboarding/2', status_code=303)


@router.get('/onboarding/2', response_class=HTMLResponse)
def onboarding_telegram_sources(error: str | None = None):
    settings = get_settings()
    mode = settings.telegram_collector_mode if settings.telegram_collector_mode in {'public', 'mtproto'} else 'public'
    notice = _error(error) if error else ''
    public_checked = ' checked' if mode == 'public' else ''
    mtproto_checked = ' checked' if mode == 'mtproto' else ''
    body = f'''<h1>Источники Telegram</h1>
    <p class="muted">Публичные каналы через t.me/s работают без дополнительных credentials.</p>{notice}
    <form method="post" action="/onboarding/2">
      <label class="choice"><input type="radio" name="mode" value="public"{public_checked}> <b>Публичные каналы</b><div class="muted">Рекомендуемый режим для старта. Никаких дополнительных ключей.</div></label>
      <label class="choice"><input type="radio" name="mode" value="mtproto"{mtproto_checked}> <b>Расширенный MTProto</b><div class="muted">Сохранить API ID/API Hash для будущей authenticated-session авторизации.</div></label>
      <div class="field"><label>Telegram API ID</label><input name="api_id" value="{html.escape(settings.telegram_collector_api_id or '')}" inputmode="numeric"></div>
      <div class="field"><label>Telegram API Hash</label><input type="password" name="api_hash" value="" placeholder="Оставьте пустым, если используете public mode"></div>
      <div class="warn">MTProto session ещё не создаётся wizard'ом автоматически. До её активации используйте public collector; сохранённые API credentials не считаются подключённой session.</div>
      <div class="row"><button class="btn secondary" type="button" onclick="location.href='/onboarding/1'">Назад</button><button class="btn good">Сохранить и далее</button></div>
    </form>'''
    return _page(2, 'Telegram-источники', body)


@router.post('/onboarding/2')
def onboarding_telegram_sources_save(
    mode: str = Form('public'),
    api_id: str = Form(''),
    api_hash: str = Form(''),
):
    try:
        save_telegram_collector_setup(mode=mode, api_id=api_id, api_hash=api_hash)
    except ValueError as exc:
        return onboarding_telegram_sources(error=str(exc))
    return RedirectResponse('/onboarding/3', status_code=303)


@router.get('/onboarding/3', response_class=HTMLResponse)
def onboarding_vk(error: str | None = None, checked: str | None = None):
    settings = get_settings()
    notice = _error(error) if error else (f'<div class="ok">{html.escape(checked)}</div>' if checked else '')
    configured = '<div class="ok">VK token уже сохранён. Чтобы заменить его, введите новый.</div>' if settings.vk_access_token else ''
    body = f'''<h1>VK</h1><p class="muted">VK нужен только для источников с collector <code>vk_api</code>. Этот шаг можно пропустить.</p>{notice}{configured}
    <form method="post" action="/onboarding/3">
      <div class="field"><label>VK Access Token</label><input type="password" name="access_token" placeholder="Необязательно"><div class="secret-note">Секрет не показывается после сохранения.</div></div>
      <div class="field"><label>VK API Version</label><input name="api_version" value="{html.escape(settings.vk_api_version)}"></div>
      <div class="row"><a class="btn secondary" href="/onboarding/2">Назад</a><button class="btn secondary" name="action" value="skip">Пропустить</button><button class="btn secondary" name="action" value="test">Проверить</button><button class="btn good" name="action" value="save">Сохранить и далее</button></div>
    </form>'''
    return _page(3, 'VK', body)


@router.post('/onboarding/3')
def onboarding_vk_save(
    access_token: str = Form(''),
    api_version: str = Form('5.199'),
    action: str = Form('save'),
):
    if action == 'skip':
        return RedirectResponse('/onboarding/4', status_code=303)
    token_to_save = access_token
    if not token_to_save and get_settings().vk_access_token:
        token_to_save = get_settings().vk_access_token or ''
    try:
        save_vk_setup(access_token=token_to_save, api_version=api_version)
    except ValueError as exc:
        return onboarding_vk(error=str(exc))
    if action == 'test':
        ok, detail = _test_vk(token_to_save, api_version)
        if not ok:
            return onboarding_vk(error=detail)
        return onboarding_vk(checked=detail)
    return RedirectResponse('/onboarding/4', status_code=303)


@router.get('/onboarding/4', response_class=HTMLResponse)
def onboarding_sources():
    body = '''<h1>Источники</h1><p class="muted">Базовые collectors уже включены в приложение. Сами конкретные сайты/каналы добавляются в реестр на странице «Источники».</p>
    <div class="check"><b>✓ Сайты промокодов</b><div class="muted">5 legacy adapters; включение хранится в БД.</div></div>
    <div class="check"><b>✓ Сайты магазинов</b><div class="muted">Generic Web Collector + bounded discovery страниц акций.</div></div>
    <div class="check"><b>✓ Telegram</b><div class="muted">Публичные t.me/s каналы без credentials.</div></div>
    <div class="check"><b>✓ VK</b><div class="muted">Через API, когда задан VK token.</div></div>
    <div class="check"><b>✓ Дзен</b><div class="muted">Public collector, credentials не требуются.</div></div>
    <div class="check"><b>✓ Rutube</b><div class="muted">Public metadata collector, credentials не требуются.</div></div>
    <div class="row" style="margin-top:20px"><a class="btn secondary" href="/onboarding/3">Назад</a><a class="btn good" href="/onboarding/5">Проверить систему</a></div>'''
    return _page(4, 'Источники', body)


@router.get('/onboarding/5', response_class=HTMLResponse)
def onboarding_check():
    report = build_doctor_report(check_web_port=False)
    rows: list[str] = []
    for check in report.checks:
        if check.ok:
            cls, mark = 'goodtext', '✓'
        elif check.required:
            cls, mark = 'badtext', '✗'
        else:
            cls, mark = 'optional', '!'
        required = '' if check.required else ' · необязательно'
        rows.append(
            f'<div class="check"><span class="status {cls}">{mark} {html.escape(check.name)}</span>'
            f'<div class="muted">{html.escape(check.detail)}{required}</div></div>'
        )
    ready = report.ok and is_setup_complete()
    if ready:
        action = '<form method="post" action="/onboarding/finish"><button class="btn good">Запустить Discount Parser</button></form>'
        intro = '<div class="ok">Обязательные проверки пройдены. Необязательные интеграции можно подключить позже.</div>'
    else:
        action = '<a class="btn good" href="/onboarding/1">Исправить настройки</a>'
        intro = '<div class="error">Есть обязательные проблемы. Исправьте их перед запуском.</div>'
    body = f'''<h1>Проверка</h1>{intro}{''.join(rows)}<div class="row" style="margin-top:20px"><a class="btn secondary" href="/onboarding/4">Назад</a>{action}</div>'''
    return _page(5, 'Проверка', body)


@router.post('/onboarding/finish')
def onboarding_finish():
    if not is_setup_complete():
        return RedirectResponse('/onboarding/1', status_code=303)
    if not build_doctor_report(check_web_port=False).ok:
        return RedirectResponse('/onboarding/5', status_code=303)
    if getattr(sys, 'frozen', False):
        for name in ('bot', 'scheduler'):
            try:
                process_manager.start(name)
            except Exception:
                pass
    return RedirectResponse('/?message=Настройка+завершена', status_code=303)
