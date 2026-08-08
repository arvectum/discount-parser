from __future__ import annotations

import sys
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from src.web.app import app
from src.web.management_pages import router as management_router
from src.web.processes import process_manager
from src.web.setup import is_setup_complete
from src.web.system_routes import router as system_router

app.include_router(management_router)
app.include_router(system_router)

_LOCAL_HOSTS = {'127.0.0.1', 'localhost', '::1'}
_MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def _is_local_url(value: str) -> bool:
    try:
        return (urlparse(value).hostname or '').lower() in _LOCAL_HOSTS
    except ValueError:
        return False


class LocalOriginMiddleware(BaseHTTPMiddleware):
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
        return response


app.add_middleware(LocalOriginMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

__all__ = ['app']
