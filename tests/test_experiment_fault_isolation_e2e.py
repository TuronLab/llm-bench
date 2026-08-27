"""
End-to-end regression test for fault isolation through the real REST API.

This exercises `backend.app.services.experiment_service` exactly as the API
does (create -> run -> poll), with fake providers/harness calls standing in
for Docker and lm-evaluation-harness so it runs anywhere without
dependencies. It specifically guards against a real bug found during
development: an early version only caught `(ProviderError, ValueError)`
when a provider failed to start, so any other exception type (a Docker SDK
error, an httpx timeout, ...) escaped, tripped the top-level safety net, and
incorrectly failed every remaining model in the experiment instead of just
the broken one.

Run with:
    PYTHONPATH=. python -m tests.test_experiment_fault_isolation_e2e
"""

from __future__ import annotations

import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from providers.base import ModelInfo, ProviderStatus
from storage.schemas import BenchmarkResult, ResultMetadata

client = TestClient(app)


class _FakeSingleModelProvider:
    """Stands in for vLLM/llama.cpp: fails to start for one specific model."""

    def __init__(self, config, fail_models: set[str]):
        self.config = config
        self.status = ProviderStatus.STOPPED
        self._fail_models = fail_models

    def start(self):
        model = self.config.options.get("model")
        if model in self._fail_models:
            # Deliberately a generic exception, NOT ProviderError, to prove
            # the fix isn't type-specific.
            raise Exception(f"simulated failure starting provider for {model}")

    def wait_until_ready(self, timeout=300, poll_interval=2):
        pass

    def stop(self):
        pass

    def list_models(self):
        return [ModelInfo(id="x", name="x")]

    def endpoint(self):
        return "http://fake/v1"

    def harness_model_type(self):
        return "local-chat-completions"

    def harness_model_args(self, model):
        return f"model={model}"


def _fake_run_benchmark(provider, model, benchmark, experiment_id, job_id, extra_args=None, on_log_line=None):
    return BenchmarkResult(
        metadata=ResultMetadata(model=model, provider=provider.config.name, benchmark=benchmark),
        metrics={"acc": 0.5},
        raw={},
    )


def _run_experiment_and_wait(definition: dict) -> dict:
    r = client.post("/api/v1/experiments", json=definition)
    assert r.status_code == 201, r.text
    exp_id = r.json()["id"]

    r = client.post(f"/api/v1/experiments/{exp_id}/run")
    assert r.status_code == 200, r.text

    record = None
    for _ in range(100):
        record = client.get(f"/api/v1/experiments/{exp_id}").json()
        if record["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert record is not None
    return record


def test_single_model_provider_start_failure_is_isolated_to_that_model():
    """
    A vLLM-style provider that fails to start for ONE model must not affect
    the other models in the same experiment.
    """
    with patch(
        "backend.app.services.experiment_service.create_provider",
        side_effect=lambda cfg: _FakeSingleModelProvider(cfg, fail_models={"broken-model"}),
    ), patch(
        "backend.app.services.experiment_service.run_benchmark",
        side_effect=_fake_run_benchmark,
    ):
        definition = {
            "name": "e2e-single-model-provider-failure",
            "provider": {"type": "vllm", "options": {}},
            "models": ["good-model-1", "broken-model", "good-model-2"],
            "benchmarks": ["mmlu", "gsm8k"],
            "execution": {"mode": "sequential", "workers": 1},
        }
        record = _run_experiment_and_wait(definition)

    statuses_by_model: dict[str, set[str]] = {}
    for job in record["jobs"]:
        statuses_by_model.setdefault(job["model"], set()).add(job["status"])

    assert statuses_by_model["good-model-1"] == {"completed"}
    assert statuses_by_model["good-model-2"] == {"completed"}
    assert statuses_by_model["broken-model"] == {"failed"}
    assert record["status"] == "completed", "partial success must still be an overall COMPLETED experiment"


if __name__ == "__main__":
    test_single_model_provider_start_failure_is_isolated_to_that_model()
    print("End-to-end fault isolation regression test passed.")
