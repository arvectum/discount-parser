from __future__ import annotations

import atexit
import ctypes
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


class _WindowsBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ('per_process_user_time_limit', ctypes.c_longlong),
        ('per_job_user_time_limit', ctypes.c_longlong),
        ('limit_flags', ctypes.c_uint32),
        ('minimum_working_set_size', ctypes.c_size_t),
        ('maximum_working_set_size', ctypes.c_size_t),
        ('active_process_limit', ctypes.c_uint32),
        ('affinity', ctypes.c_size_t),
        ('priority_class', ctypes.c_uint32),
        ('scheduling_class', ctypes.c_uint32),
    ]


class _WindowsIoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        'read_operation_count', 'write_operation_count',
        'other_operation_count', 'read_transfer_count',
        'write_transfer_count', 'other_transfer_count',
    )]


class _WindowsExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ('basic_limit_information', _WindowsBasicLimitInformation),
        ('io_info', _WindowsIoCounters),
        ('process_memory_limit', ctypes.c_size_t),
        ('job_memory_limit', ctypes.c_size_t),
        ('peak_process_memory_used', ctypes.c_size_t),
        ('peak_job_memory_used', ctypes.c_size_t),
    ]


class _WindowsWorkerJob:
    """Own a frozen worker tree for the lifetime of this web-panel session.

    PyInstaller ``--onefile`` starts a bootstrap process which can in turn
    spawn the actual worker executable.  Terminating just the bootstrap PID
    leaves that child alive.  A Windows Job Object makes every descendant
    created by the worker part of this panel's private process tree and kills
    that tree when the job handle is closed.
    """

    _KILL_ON_JOB_CLOSE = 0x00002000
    _EXTENDED_LIMIT_INFORMATION = 9

    def __init__(self, process: subprocess.Popen) -> None:
        self._handle: int | None = None
        if sys.platform != 'win32':
            return
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), 'CreateJobObjectW failed')
        info = _WindowsExtendedLimitInformation()
        info.basic_limit_information.limit_flags = self._KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            handle, self._EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), 'SetInformationJobObject failed')
        if not kernel32.AssignProcessToJobObject(handle, process._handle):
            kernel32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), 'AssignProcessToJobObject failed')
        self._handle = int(handle)

    def close(self) -> None:
        if self._handle is None:
            return
        ctypes.WinDLL('kernel32', use_last_error=True).CloseHandle(self._handle)
        self._handle = None


@dataclass(slots=True)
class _OwnedProcess:
    process: subprocess.Popen
    job: _WindowsWorkerJob | None = None


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
        self._processes: dict[str, _OwnedProcess] = {}
        atexit.register(self.stop_all)

    def _cleanup(self) -> None:
        for name, owned in list(self._processes.items()):
            if owned.process.poll() is not None:
                if owned.job is not None:
                    owned.job.close()
                self._processes.pop(name, None)

    def state(self, name: str) -> ProcessState:
        with self._lock:
            self._cleanup()
            owned = self._processes.get(name)
            return ProcessState(name=name, running=owned is not None, pid=owned.process.pid if owned else None)

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
                return ProcessState(name=name, running=True, pid=existing.process.pid)

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
            try:
                job = _WindowsWorkerJob(process) if sys.platform == 'win32' else None
            except Exception:
                process.terminate()
                process.wait(timeout=5)
                raise
            self._processes[name] = _OwnedProcess(process=process, job=job)
            return ProcessState(name=name, running=True, pid=process.pid)

    def stop(self, name: str) -> ProcessState:
        with self._lock:
            self._cleanup()
            owned = self._processes.pop(name, None)
            if owned is None:
                return ProcessState(name=name, running=False, pid=None)
            process = owned.process
            # Ask the root process to stop before forcing its owned Job tree.
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            if owned.job is not None:
                # KILL_ON_JOB_CLOSE handles the one-file bootstrap child too.
                owned.job.close()
            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # PID is from this manager's Popen handle; /T is therefore
                    # restricted to this owned tree, never a global image kill.
                    if sys.platform == 'win32':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False, capture_output=True)
                    else:
                        process.kill()
                    process.wait(timeout=5)
            return ProcessState(name=name, running=False, pid=None)

    def stop_all(self) -> None:
        for name in ('bot', 'scheduler'):
            self.stop(name)


process_manager = ProcessManager()
