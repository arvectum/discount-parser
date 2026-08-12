from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from src.modules.source_registry.service import add_keyword
from src.shared.db import session_scope

router = APIRouter()


@router.post('/sources-registry/keywords/add')
def keyword_add_static(
    keyword: str = Form(...),
    kind: str = Form('positive'),
    merchant: str = Form(''),
    priority: int = Form(50),
):
    """Static route must be registered before /{source_id}/{action}."""
    try:
        with session_scope() as session:
            add_keyword(session, keyword, kind=kind, merchant=merchant or None, priority=priority)
    except Exception as exc:
        return RedirectResponse('/sources-registry?error=' + quote(f'{type(exc).__name__}: {exc}'), status_code=303)
    return RedirectResponse('/sources-registry?message=' + quote('Ключевое слово добавлено'), status_code=303)
