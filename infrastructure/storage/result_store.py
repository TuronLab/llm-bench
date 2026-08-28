"""
File-backed persistence for benchmark results.

Layout: `results/benchmarks/<sanitized-model-name>.json`, containing a list of
`BenchmarkResult` entries that accumulate across runs. Results are never
overwritten implicitly -- a rerun of the same (model, benchmark) pair is
appended as a new entry, timestamped, so history is preserved. Callers that
explicitly want only the latest run per benchmark should use
`latest_by_benchmark`.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Optional

from infrastructure.storage.paths import BENCHMARK_RESULTS_DIR, ensure_directories
from infrastructure.storage.schemas import BenchmarkResult

logger = logging.getLogger("benchlab.storage.results")

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def sanitize_model_name(model: str) -> str:
    return _SAFE_NAME_RE.sub("_", model).strip("_") or "unknown-model"


class ResultStore:
    def __init__(self, directory: Optional[Path] = None):
        ensure_directories()
        self._dir = directory or BENCHMARK_RESULTS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, model: str) -> Path:
        return self._dir / f"{sanitize_model_name(model)}.json"

    def append(self, result: BenchmarkResult, overwrite: bool = False) -> Path:
        """
        Append a result to the model's result file. If `overwrite` is True,
        any prior entry for the same benchmark is replaced instead of a new
        entry being appended (used when the user explicitly reruns and asks
        to overwrite).
        """
        with self._lock:
            path = self._path(result.metadata.model)
            existing: list[dict] = []
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
            new_entry = json.loads(result.model_dump_json())
            new_meta = new_entry.get("metadata", {})
            new_key = (
                new_meta.get("benchmark"), new_meta.get("provider"),
                json.dumps(new_meta.get("metadata", {}), sort_keys=True, default=str),
            )
            # A configuration identifies one result. Re-running it refreshes
            # the existing entry instead of creating another dashboard row.
            existing = [e for e in existing if (
                e.get("metadata", {}).get("benchmark"),
                e.get("metadata", {}).get("provider"),
                json.dumps(e.get("metadata", {}).get("metadata", {}), sort_keys=True, default=str),
            ) != new_key]
            existing.append(new_entry)
            path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            logger.info("Stored result for model=%s benchmark=%s -> %s",
                        result.metadata.model, result.metadata.benchmark, path)
            return path

    def load(self, model: str) -> list[BenchmarkResult]:
        path = self._path(model)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [BenchmarkResult.model_validate(entry) for entry in data]

    def delete_latest(self, model: str, benchmark: str, timestamp: str | None = None) -> bool:
        """Delete the result currently shown for a model/benchmark."""
        with self._lock:
            path = self._path(model)
            if not path.exists():
                return False
            entries = json.loads(path.read_text(encoding="utf-8"))
            candidates = [e for e in entries if e.get("metadata", {}).get("benchmark") == benchmark]
            if not candidates:
                return False
            if timestamp:
                candidates = [e for e in candidates if e.get("metadata", {}).get("timestamp") == timestamp]
                if not candidates:
                    return False
            target = max(candidates, key=lambda e: e.get("metadata", {}).get("timestamp", ""))
            entries.remove(target)
            path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
            return True

    def latest_by_benchmark(self, model: str) -> dict[str, BenchmarkResult]:
        latest: dict[str, BenchmarkResult] = {}
        for result in self.load(model):
            key = result.metadata.benchmark
            if key not in latest or result.metadata.timestamp > latest[key].metadata.timestamp:
                latest[key] = result
        return latest

    def list_models(self) -> list[str]:
        # Use the model identifier stored in the result, not the sanitized
        # filename (e.g. ``llama3.2:1b`` vs ``llama3.2_1b``).
        models: set[str] = set()
        for path in self._dir.glob("*.json"):
            try:
                entries = json.loads(path.read_text(encoding="utf-8"))
                models.update(
                    entry.get("metadata", {}).get("model", "")
                    for entry in entries
                    if entry.get("metadata", {}).get("model")
                )
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(models) or sorted(p.stem for p in self._dir.glob("*.json"))

    def dashboard_matrix(self) -> dict[str, dict[str, Optional[dict]]]:
        """
        Build the model x benchmark matrix used by the dashboard summary
        view: {model: {benchmark: {"primary_metric": ..., "value": ...}}}.
        """
        matrix: dict[str, dict[str, Optional[dict]]] = {}
        for model in self.list_models():
            results = self.load(model)
            latest: dict[tuple[str, str, str], BenchmarkResult] = {}
            for result in results:
                key = (result.metadata.benchmark, result.metadata.provider, json.dumps(result.metadata.metadata, sort_keys=True, default=str))
                if key not in latest or result.metadata.timestamp > latest[key].metadata.timestamp:
                    latest[key] = result

            by_benchmark: dict[str, list[dict]] = {}
            for (benchmark, _provider, _configuration), result in latest.items():
                by_benchmark.setdefault(benchmark, []).append(_primary_score(result))

            matrix[model] = {
                benchmark: _aggregate_scores(scores)
                for benchmark, scores in by_benchmark.items()
            }
        return matrix


def _primary_score(result: BenchmarkResult) -> dict:
    """
    lm-evaluation-harness reports several metrics per task (acc, acc_norm,
    exact_match, ...). We surface the first metric as the "primary" one for
    the summary matrix, while the detailed view exposes everything in
    `result.metrics`.
    """
    metrics = result.metrics or {}
    primary_key = next(iter(metrics), None)
    return {
        "provider": result.metadata.provider,
        "metadata": result.metadata.metadata,
        "primary_metric": primary_key,
        "value": metrics.get(primary_key) if primary_key else None,
        "all_metrics": metrics,
        "timestamp": result.metadata.timestamp.isoformat(),
    }


def _aggregate_scores(scores: list[dict]) -> dict:
    """Return the historical summary value and retain provider-level scores."""
    values = [score["value"] for score in scores if isinstance(score.get("value"), (int, float))]
    return {
        "primary_metric": scores[0].get("primary_metric"),
        "value": sum(values) / len(values) if values else None,
        "providers": sorted(scores, key=lambda score: score.get("provider", "")),
    }


# Keep the module-level name stable for API services and third-party callers;
# only the implementation changes with the configured persistence backend.
from infrastructure.storage.persistence import persistence_backend, sqlite_store  # noqa: E402

result_store = sqlite_store() if persistence_backend() == "sqlite" else ResultStore()
