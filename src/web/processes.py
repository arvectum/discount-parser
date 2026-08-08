from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

ROOT = Path.cwd() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class ProcessState:
    name: str
    running: bool
    pid: int | None


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

            if getattr(sys, 'frozen', False):
                command = [sys.executable, name]
            else:
                command = [sys.executable, '-m', 'src.cli', name]

            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
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
