from __future__ import annotations

import html
import threading
from datetime import datetime

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from src.jobs.status import get_source_run_statuses
from src.modules.offers.models import Offer
from src.shared.config import get_settings
from src.shared.db import create_session
from src.sources.runner import run_all
from src.web.processes import process_manager
from src.web.setup import is_setup_complete, save_telegram_setup

app = FastAPI(title='Discount Parser Control Panel', docs_url=None, redoc_url=None)
_parse_lock = threading.Lock()
_parse_state = {'running': False, 'last_error': None, 'last_finished': None}

STYLE = '''
<style>
:root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#18212f;background:#f5f7fb}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1180px;margin:auto;padding:32px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px}.brand h1{margin:0;font-size:28px}.muted{color:#64748b}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:24px 0}.card{background:white;border:1px solid #e5e7eb;border-radius:16px;padding:18px;box-shadow:0 6px 20px rgba(15,23,42,.05)}.metric{font-size:28px;font-weight:700;margin-top:5px}.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.btn{display:inline-block;border:0;border-radius:10px;padding:10px 14px;font-weight:600;cursor:pointer;text-decoration:none;background:#111827;color:white}.btn.secondary{background:#e5e7eb;color:#111827}.btn.good{background:#0f766e}.btn.bad{background:#b91c1c}.pill{display:inline-block;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:700}.on{background:#dcfce7;color:#166534}.off{background:#fee2e2;color:#991b1b}.section{margin-top:20px}.source{display:grid;grid-template-columns:1.4fr .7fr .7fr 1fr;gap:10px;padding:10px 0;border-bottom:1px solid #eef2f7}.setup{max-width:680px;margin:50px auto;background:white;padding:30px;border-radius:18px;border:1px solid #e5e7eb}.field{margin:16px 0}.field label{display:block;font-weight:650;margin-bottom:6px}.field input{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:9px;font-size:15px}.error{background:#fee2e2;color:#991b1b;padding:12px;border-radius:10px}.ok{background:#dcfce7;color:#166534;padding:12px;border-radius:10px}@media(max-width:700px){.source{grid-template-columns:1fr 1fr}.wrap{padding:18px}}
</style>
'''


def _layout(title: str, body: str) -> str:
    return f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>{STYLE}</head><body>{body}</body></html>'


def _metrics() -> dict[str, int]:
    with create_session() as session:
        total = int(session.scalar(select(func.count()).select_from(Offer)) or 0)
        result = {'total': total}
        for status in ('ready', 'needs_review', 'published', 'expired'):
            result[status] = int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == status)) or 0)
        return result


def _run_parse_thread() -> None:
    if not _parse_lock.acquire(blocking=False):
        return
    _parse_state['running'] = True
    _parse_state['last_error'] = None
    try:
        run_all(path=get_settings().sources_config_path)
    except Exception as exc:
        _parse_state['last_error'] = f'{type(exc).__name__}: {exc}'
    finally:
        _parse_state['running'] = False
        _parse_state['last_finished'] = datetime.now().isoformat(timespec='seconds')
        _parse_lock.release()


@app.get('/', response_class=HTMLResponse)
def dashboard(request: Request):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)

    settings = get_settings()
    metrics = _metrics()
    states = process_manager.states()
    sources = get_source_run_statuses()
    source_rows = ''.join(
        f'<div class="source"><div><b>{html.escape(item.source_name)}</b><div class="muted">{html.escape(item.source_key)}</div></div>'
        f'<div>{html.escape(item.last_status or "never")}</div><div>{item.fetched_count}</div><div class="muted">{html.escape(str(item.last_finished_at or "—"))}</div></div>'
        for item in sources
    ) or '<p class="muted">Источники ещё не запускались.</p>'

    def proc_card(name: str, label: str) -> str:
        state = states[name]
        status = '<span class="pill on">РАБОТАЕТ</span>' if state.running else '<span class="pill off">ОСТАНОВЛЕН</span>'
        action = 'stop' if state.running else 'start'
        text = 'Остановить' if state.running else 'Запустить'
        cls = 'bad' if state.running else 'good'
        return f'<div class="card"><b>{label}</b><div style="margin:12px 0">{status}</div><form method="post" action="/process/{name}/{action}"><button class="btn {cls}" type="submit">{text}</button></form></div>'

    parse_status = '<span class="pill on">ИДЁТ СБОР</span>' if _parse_state['running'] else '<span class="pill off">НЕ ЗАПУЩЕН</span>'
    parse_error = f'<div class="error" style="margin-top:10px">{html.escape(str(_parse_state["last_error"]))}</div>' if _parse_state['last_error'] else ''

    body = f'''<div class="wrap">
    <div class="top"><div class="brand"><h1>Discount Parser</h1><div class="muted">Панель управления парсером и Telegram-ботом</div></div><a class="btn secondary" href="/setup">Настройки</a></div>
    <div class="grid">
      <div class="card"><div class="muted">Всего предложений</div><div class="metric">{metrics['total']}</div></div>
      <div class="card"><div class="muted">Готово</div><div class="metric">{metrics['ready']}</div></div>
      <div class="card"><div class="muted">На проверке</div><div class="metric">{metrics['needs_review']}</div></div>
      <div class="card"><div class="muted">Опубликовано</div><div class="metric">{metrics['published']}</div></div>
      <div class="card"><div class="muted">Истекло</div><div class="metric">{metrics['expired']}</div></div>
    </div>
    <div class="grid">{proc_card('bot','Telegram-бот')}{proc_card('scheduler','Автоматическое расписание')}
      <div class="card"><b>Парсер</b><div style="margin:12px 0">{parse_status}</div><form method="post" action="/parse"><button class="btn good" {'disabled' if _parse_state['running'] else ''}>Запустить сбор сейчас</button></form><div class="muted" style="margin-top:8px">Последний запуск: {html.escape(str(_parse_state['last_finished'] or '—'))}</div>{parse_error}</div>
    </div>
    <div class="card section"><div class="row" style="justify-content:space-between"><div><b>Telegram</b><div class="muted">{html.escape(settings.telegram_bot_name or 'Бот')} → {html.escape(settings.telegram_channel_id or '')}</div></div><a class="btn secondary" href="/setup">Изменить</a></div></div>
    <div class="card section"><h3>Источники</h3><div class="source"><b>Источник</b><b>Статус</b><b>Получено</b><b>Последний запуск</b></div>{source_rows}</div>
    </div>'''
    return HTMLResponse(_layout('Discount Parser', body))


@app.get('/setup', response_class=HTMLResponse)
def setup_page(error: str | None = None):
    settings = get_settings()
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ''
    body = f'''<div class="setup"><h1>Первичная настройка</h1><p class="muted">Эти данные нужны для управления Telegram-ботом и публикации в канал. Их можно изменить позже.</p>{error_html}
    <form method="post" action="/setup">
      <div class="field"><label>Токен Telegram-бота *</label><input type="password" name="bot_token" value="" placeholder="123456789:AA..." required><div class="muted">Получается у @BotFather.</div></div>
      <div class="field"><label>Имя бота</label><input name="bot_name" value="{html.escape(settings.telegram_bot_name or '')}" placeholder="Мой бот скидок"></div>
      <div class="field"><label>Telegram-канал *</label><input name="channel_id" value="{html.escape(settings.telegram_channel_id or '')}" placeholder="@my_channel или -100..." required><div class="muted">Бот должен быть администратором канала с правом публикации.</div></div>
      <div class="field"><label>Ваш Telegram user ID *</label><input name="admin_ids" value="{html.escape(settings.telegram_admin_ids or '')}" placeholder="123456789" required><div class="muted">Этот пользователь сможет управлять ботом. Несколько ID — через запятую.</div></div>
      <button class="btn good" type="submit">Сохранить и открыть панель</button>
    </form></div>'''
    return HTMLResponse(_layout('Настройка Discount Parser', body))


@app.post('/setup')
def setup_save(
    bot_token: str = Form(...),
    bot_name: str = Form(''),
    channel_id: str = Form(...),
    admin_ids: str = Form(...),
):
    try:
        save_telegram_setup(bot_token=bot_token, bot_name=bot_name, channel_id=channel_id, admin_ids=admin_ids)
    except ValueError as exc:
        return setup_page(error=str(exc))
    return RedirectResponse('/', status_code=303)


@app.post('/parse')
def start_parse():
    if not _parse_state['running']:
        threading.Thread(target=_run_parse_thread, daemon=True).start()
    return RedirectResponse('/', status_code=303)


@app.post('/process/{name}/{action}')
def process_action(name: str, action: str):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    if action == 'start':
        process_manager.start(name)
    elif action == 'stop':
        process_manager.stop(name)
    else:
        return HTMLResponse('Unsupported action', status_code=400)
    return RedirectResponse('/', status_code=303)


@app.on_event('shutdown')
def shutdown_processes() -> None:
    process_manager.stop_all()
