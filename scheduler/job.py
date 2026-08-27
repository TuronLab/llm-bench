"""
Lightweight internal job wrapper used by the scheduler. The persisted,
API-facing representation is `storage.schemas.JobRecord`; this class pairs
that record with the runtime callable the scheduler needs to execute it.
"""

from __future__ import annotations

import dataclasses
from typing import Callable

from storage.schemas import JobRecord


@dataclasses.dataclass
class ScheduledJob:
    record: JobRecord
    # The scheduler doesn't know how to run a benchmark; it only knows how
    # to schedule an opaque callable safely with respect to provider
    # concurrency limits. `run` is bound to the specific (provider, model,
    # benchmark) tuple by the experiment service.
    run: Callable[[], None]
    provider_key: str
    supports_concurrency: bool
