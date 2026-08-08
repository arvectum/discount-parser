from __future__ import annotations

import sys

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.web.app import app
from src.web.management_pages import router as management_router
from src.web.processes import process_manager
from src.web.setup import is_setup_complete
from src.web.system_routes import router as system_router

app.include_router(management_router)
app.include_router(system_router)


class DashboardNavigationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
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
                    # The dashboard exposes process state/logs and allows retry.
                    pass

        if request.url.path != '/' or response.headers.get('content-type', '').split(';')[0] != 'text/html':
            return response

        body = b''
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode('utf-8')
        marker = '<div class="top">'
        if marker in text and 'href="/offers"' not in text:
            nav = '''<div class="tabs" style="margin:0 0 18px">
              <a href="/">Главная</a>
              <a href="/offers">Предложения</a>
              <a href="/runs">Журнал</a>
              <a href="/system">Система</a>
            </div>'''
            text = text.replace('<div class="wrap">', '<div class="wrap">' + nav, 1)
        headers = dict(response.headers)
        headers.pop('content-length', None)
        return Response(content=text, status_code=response.status_code, headers=headers, media_type='text/html')


app.add_middleware(DashboardNavigationMiddleware)

__all__ = ['app']
