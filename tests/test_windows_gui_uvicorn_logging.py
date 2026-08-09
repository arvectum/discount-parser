from __future__ import annotations

import sys

import pytest
import uvicorn

from src.web.launcher import _uvicorn_logging_kwargs


def test_frozen_windowed_runtime_disables_uvicorn_console_log_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'stdout', None)
    monkeypatch.setattr(sys, 'stderr', None)

    kwargs = _uvicorn_logging_kwargs()

    assert kwargs == {'log_config': None}
    # Regression for the customer crash: constructing Config must not invoke
    # Uvicorn's DefaultFormatter, which otherwise calls sys.stdout.isatty().
    uvicorn.Config(lambda scope, receive, send: None, **kwargs)


def test_console_backed_runtime_keeps_uvicorn_default_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, 'frozen', False, raising=False)

    assert _uvicorn_logging_kwargs() == {}
