"""Shared result presentation logic, independent of persistence backend."""

from __future__ import annotations

from infrastructure.storage.schemas import BenchmarkResult


def primary_score(result: BenchmarkResult) -> dict:
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


def aggregate_scores(scores: list[dict]) -> dict:
    values = [score["value"] for score in scores if isinstance(score.get("value"), (int, float))]
    return {
        "primary_metric": scores[0].get("primary_metric"),
        "value": sum(values) / len(values) if values else None,
        "providers": sorted(scores, key=lambda score: score.get("provider", "")),
    }
