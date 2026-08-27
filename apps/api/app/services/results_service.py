"""Read-side services powering the dashboard and results API endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from infrastructure.storage.result_store import result_store
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
