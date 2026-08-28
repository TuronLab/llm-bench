"""File-backed persistence for model load_testing measurements."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from infrastructure.storage.paths import LOAD_TESTING_RESULTS_DIR, ensure_directories
from infrastructure.storage.result_store import sanitize_model_name
from infrastructure.storage.schemas import LoadTestingResult


class LoadTestingStore:
    def __init__(self, directory: Path | None = None):
        ensure_directories()
        self._dir = directory or LOAD_TESTING_RESULTS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(self, result: LoadTestingResult) -> Path:
        with self._lock:
            path = self._dir / f"{sanitize_model_name(result.model)}.json"
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            new_entry = json.loads(result.model_dump_json())
            new_key = (result.provider, result.users, json.dumps(result.metadata, sort_keys=True, default=str))
            existing = [e for e in existing if (e.get("provider"), e.get("users"), json.dumps(e.get("metadata", {}), sort_keys=True, default=str)) != new_key]
            existing.append(new_entry)
            path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            return path

    def latest(self) -> list[LoadTestingResult]:
        with self._lock:
            latest: dict[tuple[str, str, int, str], LoadTestingResult] = {}
            for path in self._dir.glob("*.json"):
                for item in json.loads(path.read_text(encoding="utf-8")):
                    result = LoadTestingResult.model_validate(item)
                    key = (result.model, result.provider, result.users, json.dumps(result.metadata, sort_keys=True, default=str))
                    if key not in latest or result.timestamp > latest[key].timestamp:
                        latest[key] = result
            return sorted(latest.values(), key=lambda result: (result.model, result.provider, result.users))

    def delete(self, model: str, provider: str, users: int, timestamp: str) -> bool:
        path = self._dir / f"{sanitize_model_name(model)}.json"
        if not path.exists(): return False
        with self._lock:
            entries = json.loads(path.read_text(encoding="utf-8"))
            kept = [e for e in entries if not (e.get("model") == model and e.get("provider") == provider and e.get("users") == users and e.get("timestamp") == timestamp)]
            if len(kept) == len(entries): return False
            path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
            return True


load_testing_store = LoadTestingStore()
