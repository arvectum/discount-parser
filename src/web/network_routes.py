from __future__ import annotations

import html
from urllib.parse import quote

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from src.modules.source_registry.models import NETWORK_POLICIES, RegisteredSource
from src.shared.config import get_settings
from src.shared.db import create_session, session_scope
from src.shared.network import NetworkRouteError, is_loopback_url, network_router
from src.web.network_settings import save_network_settings
from src.web.setup import is_setup_complete

router = APIRouter()

_STYLE = '''<style>
:root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#18212f;background:#f5f7fb}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1180px;margin:auto;padding:28px}.nav,.row{display:flex;gap:9px;flex-wrap:wrap;align-items:center}.nav a,.btn{display:inline-block;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:650;border:0;cursor:pointer}.nav a{background:#e8edf4;color:#334155}.btn{background:#111827;color:#fff}.btn.secondary{background:#e5e7eb;color:#111827}.btn.good{background:#0f766e}.card{background:#fff;border:1px solid #e5e7eb;border-radius:15px;padding:18px;margin-top:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.field label{display:block;font-size:13px;font-weight:650;margin-bottom:5px}.field input,.field select{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff}.table{width:100%;border-collapse:collapse;font-size:13px}.table th,.table td{text-align:left;padding:9px;border-bottom:1px solid #e5e7eb;vertical-align:top}.pill{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:700;background:#e2e8f0}.on{background:#dcfce7;color:#166534}.off{background:#fee2e2;color:#991b1b}.warn{background:#fef3c7;color:#92400e}.muted{color:#64748b}.flash{padding:12px;border-radius:10px;background:#dcfce7;color:#166534;margin-top:16px}.err{padding:12px;border-radius:10px;background:#fee2e2;color:#991b1b;margin-top:16px}.scroll{overflow:auto}h1,h2,h3{margin-top:0}</style>'''


def _layout(body: str) -> HTMLResponse:
    nav = '<div class="nav"><a href="/">Главная</a><a href="/sources-registry">Источники</a><a href="/offers">Предложения</a><a href="/system">Система</a><a href="/network">Сеть</a></div>'
    return HTMLResponse(f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Сеть — Discount Parser</title>{_STYLE}</head><body><div class="wrap"><div class="row" style="justify-content:space-between"><div><h1>Сеть</h1><div class="muted">Split routing для панели, Telegram и источников</div></div>{nav}</div>{body}</div></body></html>')


def _selected(value: str, current: str) -> str:
    return ' selected' if value == current else ''


def _diagnostics() -> str:
    settings = get_settings()
    targets = [
        ("Панель управления", f"http://127.0.0.1:{settings.web_port}/health", "direct"),
        ("Telegram Bot API", "https://api.telegram.org", settings.telegram_network_route or "auto"),
        ("Telegram public", "https://t.me", "auto"),
        ("VK API", "https://api.vk.com", "auto"),
        ("Дзен", "https://dzen.ru", "auto"),
        ("Rutube", "https://rutube.ru", "auto"),
    ]
    rows: list[str] = []
    for label, url, requested in targets:
        routes = ["direct"] if is_loopback_url(url) else ([requested] if requested in {"direct", "proxy", "system"} else ["direct", "proxy", "system"])
        parts: list[str] = []
        for route in routes:
            if route == "proxy" and not (settings.proxy_url or "").strip():
                parts.append('<span class="pill warn">PROXY не настроен</span>')
                continue
            probe = network_router.probe(url, route=route, timeout=4.0)
            cls = "on" if probe.ok else "off"
            status = f"{route.upper()} {'✓' if probe.ok else '×'} {probe.elapsed_ms} ms ({probe.detail})"
            parts.append(f'<span class="pill {cls}">{html.escape(status)}</span>')
            if probe.ok and requested == "auto":
                break
        rows.append(f'<tr><td><b>{html.escape(label)}</b><br><span class="muted">{html.escape(url)}</span></td><td>{" ".join(parts)}</td></tr>')
    return '<div class="card"><div class="row" style="justify-content:space-between"><div><h2>Диагностика</h2><div class="muted">Проверка выполняется только по кнопке. HTTP 4xx означает, что сетевое соединение установлено; 5xx/timeout/connect error — нет.</div></div><form method="post" action="/network/test"><button class="btn good">Проверить подключения</button></form></div><div class="scroll"><table class="table"><tbody>' + ''.join(rows) + '</tbody></table></div></div>'


@router.get('/network', response_class=HTMLResponse)
def network_page(message: str | None = None, error: str | None = None, tested: int = 0):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    settings = get_settings()
    flash = f'<div class="flash">{html.escape(message)}</div>' if message else ''
    err = f'<div class="err">{html.escape(error)}</div>' if error else ''
    password_status = '<span class="pill on">пароль сохранён</span>' if settings.proxy_password else '<span class="pill warn">пароль не задан</span>'
    mode_options = ''.join(f'<option value="{route}"{_selected(route, settings.network_mode)}>{route.upper()}</option>' for route in ("auto", "direct", "proxy", "system"))
    telegram_options = ''.join(f'<option value="{route}"{_selected(route, settings.telegram_network_route)}>{route.upper()}</option>' for route in ("auto", "direct", "proxy", "system"))

    with create_session() as session:
        sources = session.scalars(select(RegisteredSource).order_by(RegisteredSource.platform, RegisteredSource.name)).all()
    source_rows = []
    for source in sources:
        options = ''.join(f'<option value="{route}"{_selected(route, source.network_policy or "auto")}>{route.upper()}</option>' for route in NETWORK_POLICIES)
        source_rows.append(f'<tr><td><b>{html.escape(source.name)}</b><br><span class="muted">{html.escape(source.platform)} · {html.escape(source.url[:75])}</span></td><td><form class="row" method="post" action="/network/source/{source.id}"><select name="network_policy" style="padding:8px">{options}</select><button class="btn secondary">Сохранить</button></form></td></tr>')

    body = f'''{flash}{err}<div class="card"><h2>Маршрутизация</h2><p class="muted">Локальная панель всегда использует DIRECT для 127.0.0.1/localhost/::1. Глобальный AUTO пробует доступные маршруты и ненадолго запоминает рабочий маршрут домена.</p><form method="post" action="/network/save"><div class="grid"><div class="field"><label>Глобальный режим</label><select name="network_mode">{mode_options}</select></div><div class="field"><label>Маршрут Telegram</label><select name="telegram_network_route">{telegram_options}</select></div><div class="field"><label>Proxy URL</label><input name="proxy_url" value="{html.escape(settings.proxy_url or '')}" placeholder="http://127.0.0.1:7890 или socks5://127.0.0.1:1080"></div><div class="field"><label>Proxy login</label><input name="proxy_username" value="{html.escape(settings.proxy_username or '')}"></div><div class="field"><label>Proxy password {password_status}</label><input type="password" name="proxy_password" value="" placeholder="пусто = оставить текущий"></div><div class="field"><label>NO_PROXY</label><input name="no_proxy" value="{html.escape(settings.no_proxy)}"></div></div><p class="muted">TUN-only VPN без локального HTTP/SOCKS endpoint продолжает управлять маршрутом ОС. Для настоящего split routing по доменам VPN-клиент должен предоставлять локальный proxy port.</p><button class="btn good">Сохранить сеть</button></form></div>'''
    if tested:
        body += _diagnostics()
    else:
        body += '<div class="card"><div class="row"><form method="post" action="/network/test"><button class="btn good">Проверить подключения</button></form><span class="muted">Проверит localhost, Telegram, VK, Дзен и Rutube.</span></div></div>'
    body += f'<div class="card"><h2>Маршрут по источникам</h2><div class="muted">AUTO — стандарт. Закрепляйте DIRECT/PROXY только для источников, где это реально необходимо.</div><div class="scroll"><table class="table"><thead><tr><th>Источник</th><th>Network policy</th></tr></thead><tbody>{"".join(source_rows)}</tbody></table></div></div>'
    return _layout(body)


@router.post('/network/save')
def save_network_route(
    network_mode: str = Form('auto'),
    telegram_network_route: str = Form('auto'),
    proxy_url: str = Form(''),
    proxy_username: str = Form(''),
    proxy_password: str = Form(''),
    no_proxy: str = Form('127.0.0.1,localhost,::1'),
):
    try:
        save_network_settings(network_mode=network_mode, telegram_network_route=telegram_network_route, proxy_url=proxy_url, proxy_username=proxy_username, proxy_password=proxy_password, no_proxy=no_proxy)
    except Exception as exc:
        return RedirectResponse('/network?error=' + quote(str(exc)), status_code=303)
    return RedirectResponse('/network?message=' + quote('Настройки сети сохранены'), status_code=303)


@router.post('/network/test')
def test_network_route():
    return RedirectResponse('/network?tested=1', status_code=303)


@router.post('/network/source/{source_id}')
def save_source_network_policy(source_id: int, network_policy: str = Form('auto')):
    policy = network_policy.strip().lower()
    if policy not in NETWORK_POLICIES:
        return RedirectResponse('/network?error=' + quote('Неизвестный network policy'), status_code=303)
    with session_scope() as session:
        row = session.get(RegisteredSource, source_id)
        if row is None:
            return RedirectResponse('/network?error=' + quote('Источник не найден'), status_code=303)
        row.network_policy = policy
    return RedirectResponse('/network?message=' + quote('Маршрут источника обновлён'), status_code=303)
