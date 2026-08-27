"""
Job scheduler: executes the queue of `ScheduledJob`s produced for an
experiment, honoring the requested execution mode.

- Sequential mode: jobs run strictly one after another.
- Parallel mode: up to `workers` jobs run concurrently, but the scheduler
  never lets two jobs against the *same* provider instance run at once
  unless that provider explicitly declares `supports_concurrency=True`.
  This is enforced with a per-provider-key lock so a single-GPU vLLM/Ollama/
  llama.cpp instance is never double-booked.

The scheduler is intentionally decoupled from *what* a job does -- it just
calls `job.run()` inside a thread pool and tracks status transitions via the
`on_status_change` callback, which the experiment service uses to persist
progress and power the live monitoring page.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
from typing import Callable, Optional

from scheduler.job import ScheduledJob
from storage.schemas import ExecutionMode, JobStatus

logger = logging.getLogger("benchlab.scheduler")


class Scheduler:
    def __init__(
        self,
        mode: ExecutionMode,
        workers: int = 1,
        on_status_change: Optional[Callable[[ScheduledJob, JobStatus, Optional[str]], None]] = None,
    ):
        self.mode = mode
        self.workers = max(1, workers) if mode == ExecutionMode.PARALLEL else 1
        self._on_status_change = on_status_change
        self._provider_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def _lock_for(self, provider_key: str) -> threading.Lock:
        with self._locks_guard:
            if provider_key not in self._provider_locks:
                self._provider_locks[provider_key] = threading.Lock()
            return self._provider_locks[provider_key]

    def _emit(self, job: ScheduledJob, status: JobStatus, error: Optional[str] = None) -> None:
        if self._on_status_change:
            self._on_status_change(job, status, error)

    def _execute(self, job: ScheduledJob) -> None:
        if self._cancelled.is_set():
            self._emit(job, JobStatus.CANCELLED)
            return

        lock = None if job.supports_concurrency else self._lock_for(job.provider_key)
        if lock:
            lock.acquire()
        try:
            self._emit(job, JobStatus.RUNNING)
            job.run()
            self._emit(job, JobStatus.COMPLETED)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed", job.record.id)
            self._emit(job, JobStatus.FAILED, str(exc))
        finally:
            if lock:
                lock.release()

    def run_all(self, jobs: list[ScheduledJob]) -> None:
        if not jobs:
            return
        if self.mode == ExecutionMode.SEQUENTIAL:
            for job in jobs:
                if self._cancelled.is_set():
                    self._emit(job, JobStatus.CANCELLED)
                    continue
                self._execute(job)
            return

        # Parallel mode: bounded thread pool. Provider-level locks above
        # ensure jobs sharing a non-concurrent provider still serialize.
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [pool.submit(self._execute, job) for job in jobs]
            concurrent.futures.wait(futures)
