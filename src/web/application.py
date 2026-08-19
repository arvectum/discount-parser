from __future__ import annotations

import logging
import sys
import traceback
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.shared.logging import redact_secrets
from src.web.app import app
from src.web.brand_v2 import BRAND_STYLE, brand_footer, brand_header
from src.web.customer_hotfixes import install_customer_hotfixes, sources_registry_hotfix
from src.web.management_pages import router as management_router
from src.web.network_routes import router as network_router
from src.web.onboarding_routes import router as onboarding_router
from src.web.processes import process_manager
from src.web.review_routes import router as review_router
from src.web.setup import is_setup_complete
from src.web.source_registry_static_routes import router as source_registry_static_router
from src.web.source_registry_routes import router as source_registry_router
from src.web.system_routes import router as system_router
from src.web.telegram_format_routes import router as telegram_format_router
from src.web.ux_routes import router as ux_router

logger = logging.getLogger("src.web.application")

app.include_router(management_router)
app.include_router(review_router)
app.include_router(source_registry_static_router)
app.include_router(source_registry_router)
app.include_router(system_router)
app.include_router(network_router)
app.include_router(onboarding_router)
app.include_router(telegram_format_router)
app.include_router(ux_router)

# Customer-facing replacements must be part of the canonical ASGI application,
# not only the desktop launcher.  This keeps the safe Sources route active for
# frozen builds, tests, alternate entrypoints and any direct ASGI import.
install_customer_hotfixes(app)

_LOCAL_HOSTS = {'127.0.0.1', 'localhost', '::1'}
_MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
_BRAND_PATCH_STYLE = '<style>.arv-header svg{display:block;width:210px;max-width:48vw;height:auto}</style>'
_TELEGRAM_FORMAT_SETTINGS_CARD = '''<article class="ux-setting"><h2>Формат публикации Telegram</h2><p>Выберите поля поста и их порядок. Изменения видны в предпросмотре и не требуют редактирования кода.</p><a class="ux-primary" href="/settings/telegram-format">Настроить формат</a></article>'''


def _is_local_url(value: str) -> bool:
    try:
        return (urlparse(value).hostname or '').lower() in _LOCAL_HOSTS
    except ValueError:
        return False


class LocalControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == 'GET' and request.url.path == '/setup':
            return RedirectResponse('/onboarding/1', status_code=303)

        # Keep the old detailed dashboard available at /advanced, but make the
        # customer-facing root open the task-oriented home page.
        if request.method == 'GET' and request.url.path == '/' and is_setup_complete():
            suffix = f'?{request.url.query}' if request.url.query else ''
            return RedirectResponse('/home' + suffix, status_code=303)

        if request.method in _MUTATING_METHODS:
            origin = request.headers.get('origin')
            referer = request.headers.get('referer')
            if origin and not _is_local_url(origin):
                return PlainTextResponse('Cross-origin request blocked', status_code=403)
            if not origin and referer and not _is_local_url(referer):
                return PlainTextResponse('Cross-origin request blocked', status_code=403)

        try:
            # DP-CUST-007: customer evidence from the 0.1.3 frozen build proved
            # that the legacy Sources endpoint could still be selected at
            # runtime even though route introspection showed the replacement.
            # Guard the exact GET path before Starlette router dispatch so the
            # safe wrapper is guaranteed to execute in every entrypoint/build.
            if request.method == 'GET' and request.url.path == '/sources-registry':
                response = sources_registry_hotfix(
                    message=request.query_params.get('message'),
                    error=request.query_params.get('error'),
                )
            else:
                response = await call_next(request)
        except Exception:
            tb = traceback.format_exc()
            clean_tb = redact_secrets(tb)
            logger.error(f"web {request.method} {request.url.path} - 500 Internal Server Error\n{clean_tb}")

            from src.shared.db import check_and_recover_db
            recovery_happened = False
            tb_lower = tb.lower()
            if "malformed" in tb_lower or "database disk image is malformed" in tb_lower or "file is not a database" in tb_lower:
                try:
                    recovery_happened = check_and_recover_db()
                except Exception as rec_exc:
                    logger.error(f"Automatic recovery attempt failed: {rec_exc}")

            error_title = "База данных восстановлена" if recovery_happened else "Произошла ошибка при обработке запроса"
            error_msg = (
                "Обнаружено повреждение базы данных. Она была автоматически сброшена, настройки Telegram сохранены. "
                "Пожалуйста, запустите сбор предложений заново."
                if recovery_happened else
                "Детали ошибки сохранены в <code>app.log</code>."
            )

            error_html = (
                "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
                f"<title>{error_title}</title><style>body{{font-family:sans-serif;padding:30px;background:#f8fafc;color:#1e293b}}"
                ".card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:24px;max-width:600px;margin:auto}"
                "h1{color:#e11d48;font-size:20px}a{color:#0284c7}</style></head><body>"
                f"<div class='card'><h1>{error_title}</h1>"
                f"<p>{error_msg}</p>"
                "<p><a href='/home'>Вернуться на главную</a></p></div></body></html>"
            )
            return HTMLResponse(content=error_html, status_code=500)

        if (
            request.method == 'POST'
            and request.url.path == '/setup'
            and response.status_code in {302, 303, 307, 308}
            and getattr(sys, 'frozen', False)
            and is_setup_complete()
        ):
            for name in ('bot', 'scheduler'):
                try:
                    process_manager.start(name)
                except Exception:
                    pass

        if response.headers.get('content-type', '').split(';')[0] != 'text/html':
            return response

        if hasattr(response, 'body_iterator'):
            body = b''
            async for chunk in response.body_iterator:
                body += chunk
        else:
            body = bytes(getattr(response, 'body', b''))
        text = body.decode('utf-8')
        if request.method == 'GET' and request.url.path == '/settings' and 'href="/settings/telegram-format"' not in text:
            marker = '<div class="ux-cards">'
            if marker in text:
                text = text.replace(marker, marker + _TELEGRAM_FORMAT_SETTINGS_CARD, 1)
        if 'id="arvectum-brand-style"' not in text:
            brand_css = BRAND_STYLE + _BRAND_PATCH_STYLE
            if '</head>' in text:
                text = text.replace('</head>', brand_css + '</head>', 1)
            else:
                text = brand_css + text
        if '<body' in text and 'class="arv-header"' not in text:
            body_end = text.find('>', text.find('<body'))
            if body_end >= 0:
                text = text[:body_end + 1] + brand_header(request.url.path) + text[body_end + 1:]
        if '</body>' in text and 'class="arv-footer"' not in text:
            text = text.replace('</body>', brand_footer() + '</body>', 1)
        headers = dict(response.headers)
        headers.pop('content-length', None)
        return Response(content=text, status_code=response.status_code, headers=headers, media_type='text/html')


app.add_middleware(LocalControlMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

__all__ = ['app']
