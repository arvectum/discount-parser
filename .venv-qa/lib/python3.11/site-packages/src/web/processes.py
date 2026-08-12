from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / 'logs'


@dataclass(frozen=True, slots=True)
class ProcessState:
    name: str
    running: bool
    pid: int | None


def process_log_path(name: str) -> Path:
    if name not in {'bot', 'scheduler'}:
        raise ValueError(f'Unsupported process: {name}')
    return LOG_DIR / f'{name}.log'


def read_process_log(name: str, *, max_chars: int = 12000) -> str:
    path = process_log_path(name)
    if not path.exists():
        return ''
    text = path.read_text(encoding='utf-8', errors='replace')
    return text[-max(1000, max_chars):]


def _frozen_worker_executable() -> Path:
    if sys.platform == 'win32':
        candidate = ROOT / 'DiscountParserWorker.exe'
        if candidate.exists():
            return candidate
    return Path(sys.executable)


class ProcessManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen] = {}

    def _cleanup(self) -> None:
        for name, process in list(self._processes.items()):
            if process.poll() is not None:
                self._processes.pop(name, None)

    def state(self, name: str) -> ProcessState:
        with self._lock:
            self._cleanup()
            process = self._processes.get(name)
            return ProcessState(name=name, running=process is not None, pid=process.pid if process else None)

    def states(self) -> dict[str, ProcessState]:
        return {name: self.state(name) for name in ('bot', 'scheduler')}

    @staticmethod
    def _command(name: str) -> list[str]:
        if getattr(sys, 'frozen', False):
            return [str(_frozen_worker_executable()), name]
        return [sys.executable, '-m', 'src.cli', name]

    def start(self, name: str) -> ProcessState:
        if name not in {'bot', 'scheduler'}:
            raise ValueError(f'Unsupported process: {name}')
        with self._lock:
            self._cleanup()
            existing = self._processes.get(name)
            if existing is not None:
                return ProcessState(name=name, running=True, pid=existing.pid)

            creationflags = 0
            if sys.platform == 'win32':
                creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = process_log_path(name)
            with log_path.open('ab') as log_handle:
                process = subprocess.Popen(
                    self._command(name),
                    cwd=ROOT,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            self._processes[name] = process
            return ProcessState(name=name, running=True, pid=process.pid)

    def stop(self, name: str) -> ProcessState:
        with self._lock:
            self._cleanup()
            process = self._processes.pop(name, None)
            if process is None:
                return ProcessState(name=name, running=False, pid=None)
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            return ProcessState(name=name, running=False, pid=None)

    def stop_all(self) -> None:
        for name in ('bot', 'scheduler'):
            self.stop(name)


process_manager = ProcessManager()
