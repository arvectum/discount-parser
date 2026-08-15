from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.web import processes


class FakeProcess:
    next_pid = 4100

    def __init__(self) -> None:
        self.pid = FakeProcess.next_pid
        FakeProcess.next_pid += 1
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            raise processes.subprocess.TimeoutExpired('fake', timeout)
        return self.returncode


class FakeJob:
    created: list['FakeJob'] = []

    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.closed = False
        self.created.append(self)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch):
    spawned: list[FakeProcess] = []

    def popen(*args, **kwargs):
        process = FakeProcess()
        spawned.append(process)
        return process

    monkeypatch.setattr(processes.subprocess, 'Popen', popen)
    monkeypatch.setattr(processes, '_WindowsWorkerJob', FakeJob)
    monkeypatch.setattr(processes.sys, 'platform', 'win32')
    FakeJob.created.clear()
    value = processes.ProcessManager()
    yield value, spawned
    value.stop_all()


def test_scheduler_start_is_idempotent(manager) -> None:
    value, spawned = manager
    first = value.start('scheduler')
    second = value.start('scheduler')
    assert first.pid == second.pid
    assert len(spawned) == 1


def test_bot_start_is_idempotent(manager) -> None:
    value, spawned = manager
    first = value.start('bot')
    second = value.start('bot')
    assert first.pid == second.pid
    assert len(spawned) == 1


def test_parallel_workers_have_one_owned_process_each(manager) -> None:
    value, spawned = manager
    scheduler = value.start('scheduler')
    bot = value.start('bot')
    assert scheduler.running and bot.running
    assert scheduler.pid != bot.pid
    assert len(spawned) == 2


def test_normal_shutdown_terminates_and_closes_each_owned_job(manager) -> None:
    value, spawned = manager
    value.start('scheduler')
    value.start('bot')
    value.stop_all()
    assert all(process.terminated for process in spawned)
    assert all(job.closed for job in FakeJob.created)
    assert not value.state('scheduler').running
    assert not value.state('bot').running


def test_dead_worker_state_is_cleaned_and_retry_is_possible(manager) -> None:
    value, spawned = manager
    value.start('scheduler')
    spawned[0].returncode = 1
    retried = value.start('scheduler')
    assert retried.running
    assert len(spawned) == 2


def test_stale_pid_never_uses_global_image_kill(manager, monkeypatch: pytest.MonkeyPatch) -> None:
    value, _ = manager
    calls: list[list[str]] = []
    monkeypatch.setattr(processes.subprocess, 'run', lambda args, **kwargs: calls.append(args) or SimpleNamespace(returncode=0))
    value.stop('bot')
    assert calls == []
