"""
File-backed persistence for experiment state.

Experiments (definitions, derived jobs, statuses, timestamps) are written to
`experiments/<id>.json` on every mutation. This is deliberately simple (no
external database required) while still satisfying the requirement that
experiment history survives backend restarts. Swapping this for a real
database later only requires reimplementing this module's interface.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

from infrastructure.storage.paths import EXPERIMENTS_DIR, ensure_directories
from infrastructure.storage.schemas import ExperimentRecord

logger = logging.getLogger("benchlab.storage.experiments")


class ExperimentStore:
    """Thread-safe CRUD access to experiment records persisted as JSON files."""

    def __init__(self, directory: Optional[Path] = None):
        ensure_directories()
        self._dir = directory or EXPERIMENTS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, experiment_id: str) -> Path:
        return self._dir / f"{experiment_id}.json"

    def save(self, record: ExperimentRecord) -> None:
        with self._lock:
            path = self._path(record.id)
            path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
            logger.debug("Persisted experiment %s -> %s", record.id, path)

    def get(self, experiment_id: str) -> Optional[ExperimentRecord]:
        path = self._path(experiment_id)
        if not path.exists():
            return None
        return ExperimentRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, experiment_id: str) -> bool:
        path = self._path(experiment_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_all(self) -> list[ExperimentRecord]:
        records = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                records.append(ExperimentRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                logger.exception("Failed to load experiment record from %s", path)
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records


# Module-level singleton for convenience; safe because the store itself is
# stateless beyond the filesystem and internally locked.
experiment_store = ExperimentStore()
