from __future__ import annotations

import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from src.modules.offers.models import Offer
from src.modules.publishing.filters import get_or_create_default_filter
from src.modules.publishing.service import PublishCriteria, list_publish_candidates
from src.shared.config import get_settings
from src.shared.db import create_session
from src.web.app import _parse_state, dashboard as advanced_dashboard
from src.web.processes import process_manager
from src.web.setup import is_setup_complete

router = APIRouter()

PAGE_STYLE = '''<style>
.ux-wrap{max-width:1180px;margin:auto;padding:28px}.ux-hero{display:flex;justify-content:space-between;gap:22px;align-items:flex-end;margin-bottom:20px}.ux-hero h1{margin:0 0 5px;font-size:30px}.ux-lead{color:#5d6c7c;max-width:720px}.ux-status{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.ux-stat{background:#fff;border:1px solid #dce5e9;border-radius:14px;padding:15px}.ux-stat b{display:block;font-size:25px;color:#001432;margin-top:4px}.ux-flow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:18px}.ux-step{background:#fff;border:1px solid #dce5e9;border-radius:16px;padding:19px;position:relative}.ux-step-number{font-family:"JetBrains Mono",monospace;color:#00a889;font-weight:800;font-size:13px}.ux-step h2{font-size:20px;margin:7px 0}.ux-step p{color:#64748b;min-height:44px}.ux-primary{display:inline-block;text-decoration:none;border:0;border-radius:9px;background:#00C8A0;color:#001432;padding:10px 14px;font-weight:800;cursor:pointer}.ux-secondary{display:inline-block;text-decoration:none;border:1px solid #C8D2DC;border-radius:9px;background:#fff;color:#001432;padding:9px 13px;font-weight:750;cursor:pointer}.ux-note{background:#ecfffa;border:1px solid #b3f4e5;border-radius:12px;padding:13px 15px;margin-top:18px}.ux-alert{background:#fff7e8;border:1px solid #f0d29a;border-radius:12px;padding:13px 15px;margin-top:18px}.ux-form{margin-top:12px}.ux-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:10px 0}.ux-field{display:block;color:#516173;font-size:13px;font-weight:700}.ux-field span{display:block;margin-bottom:5px}.ux-form input{width:100%;padding:9px;border:1px solid #C8D2DC;border-radius:8px;background:#fff}.ux-form-help{font-size:12px;color:#748393;margin:0 0 10px!important;min-height:0!important}.ux-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.ux-setting{background:#fff;border:1px solid #dce5e9;border-radius:15px;padding:18px}.ux-setting h2{margin:0 0 6px;font-size:19px}.ux-setting p{color:#64748b;margin:0 0 13px}.ux-guide{background:#fff;border:1px solid #dce5e9;border-radius:16px;padding:22px}.ux-guide h2{margin-top:28px}.ux-guide h2:first-child{margin-top:0}.ux-guide ol,.ux-guide ul{line-height:1.65}.ux-guide code{background:#eef3f5;border-radius:5px;padding:2px 5px}.ux-guide pre{background:#001432;color:#e9f5f3;border-radius:9px;padding:12px;overflow:auto;font-size:12px;line-height:1.5}.ux-tip{border-left:4px solid #00C8A0;background:#f4fffc;padding:10px 13px;margin:12px 0}.ux-tech{font-size:13px;color:#64748b}@media(max-width:820px){.ux-wrap{padding:18px}.ux-hero{align-items:flex-start;flex-direction:column}.ux-status{grid-template-columns:1fr 1fr}.ux-flow,.ux-cards{grid-template-columns:1fr}.ux-form-grid{grid-template-columns:1fr}.ux-step p{min-height:auto}}
</style>'''


def _page(title: str, content: str) -> HTMLResponse:
    return HTMLResponse(f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>{PAGE_STYLE}</head><body>{content}</body></html>')


def _counts() -> dict[str, int]:
    with create_session() as session:
        result = {'total': int(session.scalar(select(func.count()).select_from(Offer)) or 0)}
        for status in ('needs_review', 'ready', 'published'):
            result[status] = int(session.scalar(select(func.count()).select_from(Offer).where(Offer.status == status)) or 0)
    return result


def _queue_count() -> int:
    settings = get_settings()
    if not settings.telegram_channel_id:
        return 0
    row = get_or_create_default_filter(min_discount_percent=settings.telegram_default_min_discount)
    criteria = PublishCriteria.from_filter(row)
    criteria = PublishCriteria(
        min_discount_percent=criteria.min_discount_percent,
        category=criteria.category,
        subcategory=criteria.subcategory,
        offer_type=criteria.offer_type,
        merchant=criteria.merchant,
        source_key=criteria.source_key,
        city=criteria.city,
        region=criteria.region,
        limit=100,
    )
    with create_session() as session:
        return len(list_publish_candidates(session, channel_id=settings.telegram_channel_id, criteria=criteria))


@router.get('/home', response_class=HTMLResponse)
def home(message: str | None = None):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    counts = _counts()
    queue_count = _queue_count()
    states = process_manager.states()
    scheduler_running = states.get('scheduler').running if states.get('scheduler') else False
    bot_running = states.get('bot').running if states.get('bot') else False
    parse_running = bool(_parse_state.get('running'))

    flash = f'<div class="ux-note">{html.escape(message)}</div>' if message else ''
    automation = '<div class="ux-note">Автопубликация включена и scheduler работает.</div>' if scheduler_running and bot_running else '<div class="ux-alert">Автоматизация сейчас запущена не полностью. Проверьте раздел «Настройки» → «Система и автоматизация».</div>'
    parse_button = '<button class="ux-primary" disabled>Сбор уже идёт</button>' if parse_running else '<button class="ux-primary" type="submit">Собрать предложения</button>'

    content = f'''<main class="ux-wrap"><section class="ux-hero"><div><h1>Discount Parser</h1><div class="ux-lead">Основная работа состоит из трёх шагов: собрать предложения, проверить сомнительные и опубликовать готовые.</div></div><a class="ux-secondary" href="/help">Как пользоваться</a></section>{flash}<section class="ux-status"><div class="ux-stat"><span>Всего найдено</span><b>{counts['total']}</b></div><div class="ux-stat"><span>Нужно проверить</span><b>{counts['needs_review']}</b></div><div class="ux-stat"><span>В очереди (по фильтру)</span><b>{queue_count}</b></div><div class="ux-stat"><span>Опубликовано</span><b>{counts['published']}</b></div></section><section><h2>Что делать сейчас</h2><div class="ux-flow"><article class="ux-step"><div class="ux-step-number">ШАГ 01</div><h2>Собрать</h2><p>Запустите поиск новых скидок и промокодов. При необходимости сразу ограничьте поиск по ГЕО.</p><form class="ux-form" method="post" action="/parse"><div class="ux-form-grid"><label class="ux-field"><span>Регион (необязательно)</span><input name="region" placeholder="например, Московская область"></label><label class="ux-field"><span>Город (необязательно)</span><input name="city" placeholder="например, Москва"></label></div><p class="ux-form-help">Оставьте оба поля пустыми, чтобы собирать предложения без ограничения по ГЕО.</p>{parse_button}</form></article><article class="ux-step"><div class="ux-step-number">ШАГ 02</div><h2>Проверить</h2><p>{counts['needs_review']} предложений требуют решения человека. Исправьте данные и одобрите или отклоните.</p><a class="ux-primary" href="/review">Открыть проверку</a></article><article class="ux-step"><div class="ux-step-number">ШАГ 03</div><h2>Опубликовать</h2><p>{queue_count} предложений сейчас проходят фильтр и готовы к публикации в Telegram.</p><a class="ux-primary" href="/review?status=ready">Посмотреть готовые</a></article></div></section>{automation}<div class="ux-tech" style="margin-top:18px">Расширенные функции, сеть, источники и расписание находятся в разделе «Настройки».</div></main>'''
    return _page('Discount Parser', content)


@router.get('/settings', response_class=HTMLResponse)
def settings_page():
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    content = '''<main class="ux-wrap"><section class="ux-hero"><div><h1>Настройки</h1><div class="ux-lead">Здесь собраны параметры, которые обычно настраиваются один раз или меняются редко.</div></div></section><div class="ux-cards"><article class="ux-setting"><h2>Telegram и интеграции</h2><p>Бот, канал, Telegram collector и VK.</p><a class="ux-secondary" href="/onboarding/1">Открыть интеграции</a></article><article class="ux-setting"><h2>Источники</h2><p>Какие сайты и Telegram-каналы участвуют в сборе.</p><a class="ux-secondary" href="/sources-registry">Управлять источниками</a></article><article class="ux-setting"><h2>Сеть и VPN</h2><p>AUTO / DIRECT / PROXY / SYSTEM и диагностика доступности.</p><a class="ux-secondary" href="/network">Настроить сеть</a></article><article class="ux-setting"><h2>Система и автоматизация</h2><p>Состояние bot/scheduler, расписание, фильтр публикации и технические логи.</p><a class="ux-secondary" href="/advanced">Расширенная панель</a> <a class="ux-secondary" href="/system">Система</a></article><article class="ux-setting"><h2>Данные и XLSX</h2><p>Экспорт базы предложений и массовая корректировка через Excel.</p><a class="ux-secondary" href="/export">Скачать XLSX</a></article><article class="ux-setting"><h2>Помощь</h2><p>Установка на Windows, macOS и Linux-сервер, ежедневная работа и решение типовых проблем.</p><a class="ux-primary" href="/help">Открыть инструкцию</a></article></div></main>'''
    return _page('Настройки', content)


@router.get('/advanced', response_class=HTMLResponse)
def advanced(message: str | None = None):
    if not is_setup_complete():
        return RedirectResponse('/setup', status_code=303)
    return advanced_dashboard(message=message)


@router.get('/help', response_class=HTMLResponse)
def help_page():
    content = '''<main class="ux-wrap"><section class="ux-hero"><div><h1>Инструкция</h1><div class="ux-lead">Короткое руководство по установке и ежедневной работе с Discount Parser.</div></div></section><article class="ux-guide"><h2>1. Установка на Windows</h2><ol><li>Получите файл <code>DiscountParser-Setup.exe</code> от Арвектум.</li><li>Закройте предыдущую версию Discount Parser, если она запущена.</li><li>Запустите установщик и оставьте предложенный каталог установки. Администраторские права для обычной установки не требуются.</li><li>После установки откройте <b>Discount Parser</b> с рабочего стола или из меню «Пуск».</li><li>Панель откроется локально в браузере. При первом запуске пройдите мастер Telegram и сети.</li></ol><div class="ux-tip">При обновлении запускайте новый installer поверх существующей установки, не удаляя программу и её рабочие данные предварительно.</div><h2>2. Установка на macOS</h2><ol><li>Откройте файл <code>DiscountParser.dmg</code>.</li><li>Перетащите <b>Discount Parser.app</b> в папку Applications.</li><li>Откройте приложение. Панель запустится локально в браузере.</li><li>При первом запуске пройдите мастер настройки Telegram и сети.</li></ol><div class="ux-tip">Все рабочие данные и авторизация хранятся локально. При обычном обновлении приложения повторно вводить Telegram-токен не требуется.</div><h2>3. Установка на Linux-сервер</h2><p>Linux-версия запускается из исходной поставки под Python 3.11+. Для постоянной работы рекомендуется systemd: отдельные процессы web, bot и scheduler.</p><pre>python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install .
DP_RUNTIME_ROOT=/var/lib/discount-parser \
DP_DATABASE_URL=sqlite:////var/lib/discount-parser/discount_parser.db \
.venv/bin/python -m src.distribution_entry migrate</pre><p>Web-панель должна слушать только <code>127.0.0.1</code>. Для доступа с рабочего компьютера используйте SSH-туннель, например <code>ssh -L 8765:127.0.0.1:8765 user@server</code>, затем откройте <code>http://127.0.0.1:8765</code>.</p><div class="ux-tip">Не выставляйте локальную панель напрямую в интернет: в текущей архитектуре она рассчитана на localhost. Полная схема systemd приведена в <code>docs/USER_GUIDE_RU.md</code>.</div><h2>4. Первичная настройка</h2><ol><li>Укажите токен Telegram-бота, канал и Telegram user ID администратора.</li><li>В разделе сети сначала оставьте режим <b>AUTO</b>. Если Telegram доступен только через VPN/proxy, проверьте диагностику.</li><li>Откройте «Источники» и убедитесь, что нужные источники включены.</li></ol><h2>5. Обычная работа</h2><ol><li>На «Главной» при необходимости укажите регион и/или город и нажмите <b>Собрать предложения</b>. Оба поля ГЕО всегда видны; пустые поля означают сбор без географического ограничения.</li><li>После завершения откройте <b>Проверку</b>. Обработайте предложения со статусом needs_review.</li><li>Одобренные предложения получают статус <b>ready</b> и попадают в очередь, если проходят фильтр публикации.</li><li>Scheduler публикует очередь автоматически по заданному интервалу.</li></ol><h2>6. Как проверять предложение</h2><p>На странице «Проверка» сверяйте название, исходную ссылку, магазин, выгоду, ГЕО и условия. При необходимости исправьте данные.</p><ul><li><b>Сохранить правки</b> — оставить предложение на проверке.</li><li><b>Одобрить → ready</b> — разрешить публикацию.</li><li><b>Отклонить</b> — исключить предложение из публикации.</li></ul><div class="ux-tip">Ручные исправления защищены от перезаписи следующим парсингом.</div><h2>7. Очередь и автопостинг</h2><p>Количество «Готово» и количество в очереди могут отличаться. В очередь входят только ready-предложения, которые проходят текущий фильтр и ещё не имеют записи публикации для выбранного канала.</p><p>Старые публикации со статусом failed автоматически не повторяются, чтобы не создать дубликат после неопределённого сетевого таймаута.</p><h2>8. Сеть, VPN и proxy</h2><ul><li><b>AUTO</b> — приложение само выбирает рабочий маршрут.</li><li><b>DIRECT</b> — запрос без proxy.</li><li><b>PROXY</b> — использовать заданный HTTP/SOCKS proxy.</li><li><b>SYSTEM</b> — использовать системную сеть/VPN.</li></ul><p>Локальная панель на 127.0.0.1 всегда должна открываться напрямую. Для проблемного источника можно задать свой маршрут отдельно.</p><h2>9. Обновление</h2><p><b>Windows:</b> закройте приложение и запустите новый <code>DiscountParser-Setup.exe</code> поверх текущей установки.</p><p><b>macOS:</b> закройте приложение, откройте новый DMG и замените старый <b>Discount Parser.app</b>.</p><p><b>Linux:</b> остановите три systemd-сервиса, обновите файлы приложения, обновите зависимости, выполните migrate и снова запустите сервисы. Каталог runtime с <code>.env</code> и SQLite не удаляйте.</p><h2>10. Если что-то не работает</h2><ul><li><b>Telegram не отправляет:</b> откройте «Настройки → Сеть», запустите диагностику и проверьте маршрут Telegram.</li><li><b>Очередь пуста:</b> проверьте, есть ли ready-предложения и проходят ли они фильтр публикации.</li><li><b>Много needs_review:</b> это не ошибка — откройте «Проверка» и обработайте предложения вручную.</li><li><b>Панель не открывается:</b> убедитесь, что приложение или web-service запущены; панель работает на локальном адресе <code>127.0.0.1</code>.</li></ul><h2>11. Где находятся расширенные функции</h2><p>«Настройки → Расширенная панель» содержит расписание, bot/scheduler, фильтр публикации, XLSX и дополнительные технические параметры.</p></article></main>'''
    return _page('Инструкция', content)
