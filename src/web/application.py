from __future__ import annotations

import sys
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from src.web.app import app
from src.web.management_pages import router as management_router
from src.web.processes import process_manager
from src.web.setup import is_setup_complete
from src.web.source_registry_routes import router as source_registry_router
from src.web.system_routes import router as system_router

app.include_router(management_router)
app.include_router(source_registry_router)
app.include_router(system_router)

_LOCAL_HOSTS = {'127.0.0.1', 'localhost', '::1'}
_MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def _is_local_url(value: str) -> bool:
    try:
        return (urlparse(value).hostname or '').lower() in _LOCAL_HOSTS
    except ValueError:
        return False


class LocalControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _MUTATING_METHODS:
            origin = request.headers.get('origin')
            referer = request.headers.get('referer')
            if origin and not _is_local_url(origin):
                return PlainTextResponse('Cross-origin request blocked', status_code=403)
            if not origin and referer and not _is_local_url(referer):
                return PlainTextResponse('Cross-origin request blocked', status_code=403)

        response = await call_next(request)

        # In the installed client build, successful first-run setup should make
        # the application operational immediately. Source/development mode
        # remains explicit and does not spawn external processes automatically.
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
                    # The System page exposes state/logs and allows retry.
                    pass

        if request.url.path != '/' or response.headers.get('content-type', '').split(';')[0] != 'text/html':
            return response

        body = b''
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode('utf-8')
        if '<div class="wrap">' in text and 'href="/offers"' not in text:
            nav = '''<div class="row" style="margin:0 0 18px">
              <a class="btn secondary" href="/">Главная</a>
              <a class="btn secondary" href="/sources-registry">Источники</a>
              <a class="btn secondary" href="/offers">Предложения</a>
              <a class="btn secondary" href="/runs">Журнал</a>
              <a class="btn secondary" href="/system">Система</a>
            </div>'''
            text = text.replace('<div class="wrap">', '<div class="wrap">' + nav, 1)
        headers = dict(response.headers)
        headers.pop('content-length', None)
        return Response(content=text, status_code=response.status_code, headers=headers, media_type='text/html')


app.add_middleware(LocalControlMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

__all__ = ['app']
