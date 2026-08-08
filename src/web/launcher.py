from __future__ import annotations

import sys
import threading
import time
import webbrowser

import uvicorn

from src.shared.config import get_settings
from src.web.processes import process_manager
from src.web.setup import is_setup_complete


def _open_browser(url: str) -> None:
    time.sleep(1.0)
    webbrowser.open(url)


def _autostart_packaged_services() -> None:
    if not getattr(sys, 'frozen', False) or not is_setup_complete():
        return
    for name in ('bot', 'scheduler'):
        try:
            process_manager.start(name)
        except Exception:
            # The dashboard still opens and lets the user retry manually.
            pass


def run_web_panel() -> None:
    settings = get_settings()
    url = f'http://127.0.0.1:{settings.web_port}'
    _autostart_packaged_services()
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    from src.web.application import app

    uvicorn.run(
        app,
        host='127.0.0.1',
        port=settings.web_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
