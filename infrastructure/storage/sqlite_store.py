"""SQLite implementation of the BenchLab persistence contracts.

Each record is retained as JSON to preserve the public data shape and raw
harness output, while indexed columns provide efficient lookup and replacement
semantics equivalent to the JSON backend.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from infrastructure.storage.result_helpers import aggregate_scores, primary_score
from infrastructure.storage.schemas import BenchmarkResult, ExperimentRecord, LoadTestingResult


def _json(model) -> str:
    return model.model_dump_json()


def _config_key(value: dict) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _matches_timestamp(value: datetime, timestamp: str) -> bool:
    """Accept either ISO rendering returned by FastAPI (``Z``) or Python."""
    try:
        return value == datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return value.isoformat() == timestamp


class SQLiteStore:
    """A single local SQLite database containing experiments and all results."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS benchmark_results (
                    model TEXT NOT NULL, benchmark TEXT NOT NULL, provider TEXT NOT NULL,
                    configuration TEXT NOT NULL, timestamp TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (model, benchmark, provider, configuration)
                );
                CREATE TABLE IF NOT EXISTS load_testing_results (
                    model TEXT NOT NULL, provider TEXT NOT NULL, concurrent_users INTEGER NOT NULL,
                    configuration TEXT NOT NULL, timestamp TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (model, provider, concurrent_users, configuration)
                );
                CREATE INDEX IF NOT EXISTS idx_benchmark_results_model ON benchmark_results(model);
                CREATE INDEX IF NOT EXISTS idx_load_testing_timestamp ON load_testing_results(timestamp);
                """
            )

    def save(self, record: ExperimentRecord) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO experiments(id, created_at, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET created_at=excluded.created_at, payload=excluded.payload",
                (record.id, record.created_at.isoformat(), _json(record)),
            )

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        with self._lock:
            row = self._connection.execute("SELECT payload FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
        return ExperimentRecord.model_validate_json(row["payload"]) if row else None

    def delete(self, experiment_id: str) -> bool:
        with self._lock, self._connection:
            return self._connection.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,)).rowcount > 0

    def list_all(self) -> list[ExperimentRecord]:
        with self._lock:
            rows = self._connection.execute("SELECT payload FROM experiments ORDER BY created_at DESC").fetchall()
        return [ExperimentRecord.model_validate_json(row["payload"]) for row in rows]

    def append(self, result: BenchmarkResult, overwrite: bool = False) -> Path:
        metadata = result.metadata
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO benchmark_results(model, benchmark, provider, configuration, timestamp, payload) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(model, benchmark, provider, configuration) "
                "DO UPDATE SET timestamp=excluded.timestamp, payload=excluded.payload",
                (metadata.model, metadata.benchmark, metadata.provider, _config_key(metadata.metadata),
                 metadata.timestamp.isoformat(), _json(result)),
            )
        return self.path

    def load(self, model: str) -> list[BenchmarkResult]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM benchmark_results WHERE model = ? ORDER BY timestamp", (model,)
            ).fetchall()
        return [BenchmarkResult.model_validate_json(row["payload"]) for row in rows]

    def delete_latest(self, model: str, benchmark: str, timestamp: str | None = None) -> bool:
        candidates = [r for r in self.load(model) if r.metadata.benchmark == benchmark]
        if timestamp:
            candidates = [r for r in candidates if _matches_timestamp(r.metadata.timestamp, timestamp)]
        if not candidates:
            return False
        target = max(candidates, key=lambda r: r.metadata.timestamp)
        with self._lock, self._connection:
            return self._connection.execute(
                "DELETE FROM benchmark_results WHERE model=? AND benchmark=? AND provider=? AND configuration=?",
                (target.metadata.model, target.metadata.benchmark, target.metadata.provider,
                 _config_key(target.metadata.metadata)),
            ).rowcount > 0

    def latest_by_benchmark(self, model: str) -> dict[str, BenchmarkResult]:
        latest: dict[str, BenchmarkResult] = {}
        for result in self.load(model):
            key = result.metadata.benchmark
            if key not in latest or result.metadata.timestamp > latest[key].metadata.timestamp:
                latest[key] = result
        return latest

    def list_models(self) -> list[str]:
        with self._lock:
            rows = self._connection.execute("SELECT DISTINCT model FROM benchmark_results ORDER BY model").fetchall()
        return [row["model"] for row in rows]

    def dashboard_matrix(self) -> dict:
        matrix: dict[str, dict] = {}
        for model in self.list_models():
            latest: dict[tuple[str, str, str], BenchmarkResult] = {}
            for result in self.load(model):
                key = (result.metadata.benchmark, result.metadata.provider, _config_key(result.metadata.metadata))
                if key not in latest or result.metadata.timestamp > latest[key].metadata.timestamp:
                    latest[key] = result
            grouped: dict[str, list[dict]] = {}
            for (benchmark, _, _), result in latest.items():
                grouped.setdefault(benchmark, []).append(primary_score(result))
            matrix[model] = {benchmark: aggregate_scores(scores) for benchmark, scores in grouped.items()}
        return matrix

    def append_load_test(self, result: LoadTestingResult) -> Path:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO load_testing_results(model, provider, concurrent_users, configuration, timestamp, payload) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(model, provider, concurrent_users, configuration) "
                "DO UPDATE SET timestamp=excluded.timestamp, payload=excluded.payload",
                (result.model, result.provider, result.concurrent_users, _config_key(result.metadata),
                 result.timestamp.isoformat(), _json(result)),
            )
        return self.path

    def latest_load_tests(self) -> list[LoadTestingResult]:
        with self._lock:
            rows = self._connection.execute("SELECT payload FROM load_testing_results").fetchall()
        latest: dict[tuple[str, str, int, str], LoadTestingResult] = {}
        for row in rows:
            result = LoadTestingResult.model_validate_json(row["payload"])
            if not result.prompt and result.input.startswith("file://"):
                parsed = urlparse(result.input)
                prompt_path = Path(unquote(parsed.path))
                if parsed.netloc in (".", ".."):
                    prompt_path = Path(f"{parsed.netloc}{parsed.path}")
                try:
                    result.prompt, result.input_filename = prompt_path.read_text(encoding="utf-8"), prompt_path.name
                except OSError:
                    pass
            key = (result.model, result.provider, result.concurrent_users, _config_key(result.metadata))
            if key not in latest or result.timestamp > latest[key].timestamp:
                latest[key] = result
        return sorted(latest.values(), key=lambda r: (r.model, r.provider, r.concurrent_users))

    def delete_load_test(self, model: str, provider: str, concurrent_users: int, timestamp: str) -> bool:
        with self._lock:
            rows = self._connection.execute("SELECT payload FROM load_testing_results WHERE model=? AND provider=? AND concurrent_users=?", (model, provider, concurrent_users)).fetchall()
        for row in rows:
            result = LoadTestingResult.model_validate_json(row["payload"])
            if _matches_timestamp(result.timestamp, timestamp):
                with self._lock, self._connection:
                    return self._connection.execute(
                        "DELETE FROM load_testing_results WHERE model=? AND provider=? AND concurrent_users=? AND configuration=?",
                        (model, provider, concurrent_users, _config_key(result.metadata)),
                    ).rowcount > 0
        return False
