from __future__ import annotations

import threading
import time
import webbrowser

import uvicorn

from src.shared.config import get_settings


def _open_browser(url: str) -> None:
    time.sleep(1.0)
    webbrowser.open(url)


def run_web_panel() -> None:
    settings = get_settings()
    url = f'http://127.0.0.1:{settings.web_port}'
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    uvicorn.run(
        'src.web.app:app',
        host='127.0.0.1',
        port=settings.web_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
