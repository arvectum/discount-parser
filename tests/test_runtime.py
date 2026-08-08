from __future__ import annotations

import asyncio

import src.runtime as runtime


class FakeScheduler:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    @property
    def running(self) -> bool:
        return self.started and not self.stopped

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = True) -> None:
        assert wait is False
        self.stopped = True


def test_unified_runtime_starts_and_stops_scheduler(monkeypatch) -> None:
    scheduler = FakeScheduler()
    bot_calls: list[str] = []

    async def fake_bot() -> None:
        bot_calls.append("started")

    monkeypatch.setattr(runtime, "build_scheduler", lambda **kwargs: scheduler)
    monkeypatch.setattr(runtime, "run_bot_async", fake_bot)

    asyncio.run(runtime.run_all_async())

    assert scheduler.started is True
    assert scheduler.stopped is True
    assert bot_calls == ["started"]
