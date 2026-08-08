from __future__ import annotations

import html
import os
import threading
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from src.qa.doctor import build_doctor_report
from src.web.processes import process_log_path, process_manager, read_process_log
from src.web.setup import is_setup_complete

router = APIRouter()

STYLE = '''
<style>
:root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#18212f;background:#f5f7fb}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1100px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.nav{display:flex;gap:8px;flex-wrap:wrap}.nav a,.btn{display:inline-block;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:650;border:0;cursor:pointer}.nav a{background:#e8edf4;color:#334155}.card{background:#fff;border:1px solid #e5e7eb;border-radius:15px;padding:18px;margin-top:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.pill{display:inline-block;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:700}.on{background:#dcfce7;color:#166534}.off{background:#fee2e2;color:#991b1b}.warn{background:#fef3c7;color:#92400e}.btn{background:#111827;color:#fff}.btn.bad{background:#b91c1c}.btn.secondary{background:#e5e7eb;color:#111827}.muted{color:#64748b}.log{background:#0f172a;color:#e2e8f0;padding:13px;border-radius:10px;white-space:pre-wrap;word-break:break-word;max-height:360px;overflow:auto;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.check{display:grid;grid-template-columns:150px auto 1fr;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid #eef2f7}.check:last-child{border-bottom:0}h1,h3{margin-top:0}@media(max-width:700px){.check{grid-template-columns:1fr}}
</style>
'''


def _layout(title: str, body: str) -> HTMLResponse:
    nav = '''<div class="nav"><a href="/">Главная</a><a href="/offers">Предложения</a><a href="/runs">Журнал</a><a href="/system">Система</a></div>'''
    return HTMLResponse(
        f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>{STYLE}</head><body><div class="wrap"><div class="top"><div><h1>{html.escape(title)}</h1><div class="muted">Discount Parser</div></div>{nav}</div>{body}</div></body></html>'
    )


def _require_setup():
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    return None


def _doctor_html() -> str:
    report = build_doctor_report(check_web_port=False)
    rows: list[str] = []
    for check in report.checks:
        if check.ok:
            badge = '<span class="pill on">OK</span>'
        elif check.required:
            badge = '<span class="pill off">ОШИБКА</span>'
        else:
            badge = '<span class="pill warn">ПРОВЕРИТЬ</span>'
        rows.append(
            f'<div class="check"><b>{html.escape(check.name)}</b>{badge}<span>{html.escape(check.detail)}</span></div>'
        )
    overall = '<span class="pill on">ГОТОВО К ЛОКАЛЬНОМУ ТЕСТУ</span>' if report.ok else '<span class="pill off">ЕСТЬ БЛОКИРУЮЩИЕ ОШИБКИ</span>'
    return f'<div class="card"><div class="row" style="justify-content:space-between"><h3>Самодиагностика</h3>{overall}</div>{"".join(rows)}</div>'


@router.get('/system', response_class=HTMLResponse)
def system_page():
    redirect = _require_setup()
    if redirect:
        return redirect

    states = process_manager.states()
    cards = []
    for name, label in (('bot', 'Telegram-бот'), ('scheduler', 'Scheduler')):
        state = states[name]
        badge = '<span class="pill on">РАБОТАЕТ</span>' if state.running else '<span class="pill off">ОСТАНОВЛЕН</span>'
        pid = str(state.pid) if state.pid else '—'
        cards.append(f'<div class="card"><h3>{label}</h3><div class="row">{badge}<span class="muted">PID {pid}</span></div></div>')

    logs = []
    for name, label in (('bot', 'Telegram-бот'), ('scheduler', 'Scheduler')):
        text = read_process_log(name) or 'Лог пока пуст.'
        logs.append(
            f'<div class="card"><div class="row" style="justify-content:space-between"><h3>{label}: последние записи</h3>'
            f'<form method="post" action="/system/logs/{name}/clear"><button class="btn secondary" type="submit">Очистить лог</button></form></div>'
            f'<div class="log">{html.escape(text)}</div></div>'
        )

    body = f'''{_doctor_html()}<div class="grid">{''.join(cards)}</div>{''.join(logs)}
    <div class="card"><h3>Завершение приложения</h3><p class="muted">Остановит Telegram-бота, scheduler и локальную web-панель. После этого приложение можно снова запустить ярлыком.</p>
    <form method="post" action="/shutdown"><button class="btn bad" type="submit">Завершить Discount Parser</button></form></div>'''
    return _layout('Система', body)


@router.post('/system/logs/{name}/clear')
def clear_log(name: str):
    try:
        path: Path = process_log_path(name)
    except ValueError:
        return HTMLResponse('Unknown log', status_code=404)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('', encoding='utf-8')
    return RedirectResponse('/system', status_code=303)


def _exit_application() -> None:
    process_manager.stop_all()
    os._exit(0)


@router.post('/shutdown', response_class=HTMLResponse)
def shutdown_application():
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    threading.Timer(0.5, _exit_application).start()
    return _layout(
        'Discount Parser завершён',
        '<div class="card"><h3>Программа завершается</h3><p>Можно закрыть эту вкладку. Для следующего запуска используйте ярлык Discount Parser.</p></div>',
    )
