"""Read-side services powering the dashboard and results API endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from infrastructure.storage.result_store import result_store
from infrastructure.storage.load_testing_store import load_testing_store
from infrastructure.storage.schemas import BenchmarkResult

logger = logging.getLogger("benchlab.services.results")


def dashboard_matrix() -> dict:
    return result_store.dashboard_matrix()


def list_models() -> list[str]:
    return result_store.list_models()


def results_for_model(model: str) -> list[BenchmarkResult]:
    return result_store.load(model)


def detailed_result(model: str, benchmark: str) -> Optional[BenchmarkResult]:
    latest = result_store.latest_by_benchmark(model)
    return latest.get(benchmark)


def delete_latest_result(model: str, benchmark: str, timestamp: str | None = None) -> bool:
    return result_store.delete_latest(model, benchmark, timestamp)


def load_testing_results() -> list[dict]:
    """Latest load-test result for every model/provider/concurrency combination."""
    return [result.model_dump(mode="json") for result in load_testing_store.latest()]

def delete_load_testing_result(model: str, provider: str, concurrent_users: int, timestamp: str) -> bool:
    return load_testing_store.delete(model, provider, concurrent_users, timestamp)
