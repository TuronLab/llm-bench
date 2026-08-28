"""Regression tests for the optional SQLite persistence backend."""

from __future__ import annotations

from datetime import datetime, timezone

from infrastructure.storage.persistence import SQLiteLoadTestingRepository
from infrastructure.storage.schemas import (
    BenchmarkResult,
    ExperimentDefinition,
    ExperimentRecord,
    LoadTestingResult,
    ProviderSpec,
    ResultMetadata,
)
from infrastructure.storage.sqlite_store import SQLiteStore


def test_sqlite_store_preserves_repository_behaviour(tmp_path):
    store = SQLiteStore(tmp_path / "benchlab.db")
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    result = BenchmarkResult(
        metadata=ResultMetadata(
            model="llama:1b", provider="ollama", benchmark="mmlu", timestamp=timestamp, metadata={"limit": 5}
        ),
        metrics={"acc": 0.75},
        raw={"results": {"mmlu": {"acc": 0.75}}},
    )
    assert store.append(result) == tmp_path / "benchlab.db"
    assert store.list_models() == ["llama:1b"]
    assert store.load("llama:1b") == [result]
    assert store.latest_by_benchmark("llama:1b")["mmlu"] == result
    assert store.dashboard_matrix()["llama:1b"]["mmlu"]["value"] == 0.75

    # FastAPI serializes UTC timestamps with Z; deletion accepts that form too.
    assert store.delete_latest("llama:1b", "mmlu", "2026-01-02T03:04:05Z")
    assert store.load("llama:1b") == []


def test_sqlite_store_persists_experiments_and_load_tests(tmp_path):
    store = SQLiteStore(tmp_path / "benchlab.db")
    record = ExperimentRecord(
        definition=ExperimentDefinition(name="database run", provider=ProviderSpec(type="ollama"), models=["m"])
    )
    store.save(record)
    assert store.get(record.id) == record
    assert [item.id for item in store.list_all()] == [record.id]

    loads = SQLiteLoadTestingRepository(store)
    load_result = LoadTestingResult(
        model="m", provider="ollama", concurrent_users=2, input="hello", max_output_tokens=8, requests_per_user=1
    )
    assert loads.append(load_result) == tmp_path / "benchlab.db"
    assert loads.latest() == [load_result]
    assert loads.delete("m", "ollama", 2, load_result.timestamp.isoformat())
    assert loads.latest() == []
