"""File-backed persistence for model scalability measurements."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from infrastructure.storage.paths import SCALABILITY_RESULTS_DIR, ensure_directories
from infrastructure.storage.result_store import sanitize_model_name
from infrastructure.storage.schemas import ScalabilityResult


class ScalabilityStore:
    def __init__(self, directory: Path | None = None):
        ensure_directories()
        self._dir = directory or SCALABILITY_RESULTS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(self, result: ScalabilityResult) -> Path:
        with self._lock:
            path = self._dir / f"{sanitize_model_name(result.model)}.json"
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            existing.append(json.loads(result.model_dump_json()))
            path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            return path

    def latest(self) -> list[ScalabilityResult]:
        with self._lock:
            latest: dict[tuple[str, str, int], ScalabilityResult] = {}
            for path in self._dir.glob("*.json"):
                for item in json.loads(path.read_text(encoding="utf-8")):
                    result = ScalabilityResult.model_validate(item)
                    key = (result.model, result.provider, result.users)
                    if key not in latest or result.timestamp > latest[key].timestamp:
                        latest[key] = result
            return sorted(latest.values(), key=lambda result: (result.model, result.provider, result.users))


scalability_store = ScalabilityStore()
