from __future__ import annotations

import sys
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.web.app import app
from src.web.brand import BRAND_STYLE, brand_footer, brand_header
from src.web.management_pages import router as management_router
from src.web.network_routes import router as network_router
from src.web.onboarding_routes import router as onboarding_router
from src.web.processes import process_manager
from src.web.review_routes import router as review_router
from src.web.setup import is_setup_complete
from src.web.source_registry_static_routes import router as source_registry_static_router
from src.web.source_registry_routes import router as source_registry_router
from src.web.system_routes import router as system_router

app.include_router(management_router)
app.include_router(review_router)
app.include_router(source_registry_static_router)
app.include_router(source_registry_router)
app.include_router(system_router)
app.include_router(network_router)
app.include_router(onboarding_router)

_LOCAL_HOSTS = {'127.0.0.1', 'localhost', '::1'}
_MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
_BRAND_PATCH_STYLE = '<style>.arv-header svg{display:block;width:210px;max-width:48vw;height:auto}</style>'
_LEGAL_ADDRESS_SHORT = '129337, г. Москва, Ярославское ш., д. 107, к. 2, кв. 75'
_LEGAL_ADDRESS_FULL = '129337, г. Москва, вн. тер. г. муниципальный округ Ярославский, ш. Ярославское, д. 107, к. 2, кв. 75'


def _is_local_url(value: str) -> bool:
    try:
        return (urlparse(value).hostname or '').lower() in _LOCAL_HOSTS
    except ValueError:
        return False


class LocalControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == 'GET' and request.url.path == '/setup':
            return RedirectResponse('/onboarding/1', status_code=303)

        if request.method in _MUTATING_METHODS:
            origin = request.headers.get('origin')
            referer = request.headers.get('referer')
            if origin and not _is_local_url(origin):
                return PlainTextResponse('Cross-origin request blocked', status_code=403)
            if not origin and referer and not _is_local_url(referer):
                return PlainTextResponse('Cross-origin request blocked', status_code=403)

        response = await call_next(request)

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

        body = b''
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode('utf-8')
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
            footer = brand_footer().replace(_LEGAL_ADDRESS_SHORT, _LEGAL_ADDRESS_FULL)
            text = text.replace('</body>', footer + '</body>', 1)
        headers = dict(response.headers)
        headers.pop('content-length', None)
        return Response(content=text, status_code=response.status_code, headers=headers, media_type='text/html')


app.add_middleware(LocalControlMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

__all__ = ['app']
