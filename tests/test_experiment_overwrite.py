from infrastructure.storage.experiment_store import ExperimentStore
from infrastructure.storage.schemas import ExperimentDefinition, ProviderSpec
from apps.api.app.services import experiment_service


def _definition(benchmarks, limit=50):
    return ExperimentDefinition(
        name="test", providers=[ProviderSpec(type="ollama", options={"url": "local"})],
        models=["model"], benchmarks=benchmarks, extra_harness_args={"limit": limit},
    )


def test_equivalence_is_checked_per_benchmark_and_overwrite_bypasses_it(tmp_path, monkeypatch):
    store = ExperimentStore(tmp_path)
    monkeypatch.setattr(experiment_service, "experiment_store", store)

    first = experiment_service.create_experiment(_definition(["gsm8k"]))
    second = experiment_service.create_experiment(_definition(["gsm8k", "truthfulqa_gen"]))
    assert [job.benchmark for job in second.jobs] == ["truthfulqa_gen"]
    assert second.__dict__["skipped_items"][0]["existing_experiment_id"] == first.id

    overwritten = experiment_service.create_experiment(_definition(["gsm8k", "truthfulqa_gen"]), overwrite=True)
    assert {job.benchmark for job in overwritten.jobs} == {"gsm8k", "truthfulqa_gen"}


def test_changed_parameter_runs_the_benchmark_again(tmp_path, monkeypatch):
    store = ExperimentStore(tmp_path)
    monkeypatch.setattr(experiment_service, "experiment_store", store)
    experiment_service.create_experiment(_definition(["gsm8k"], limit=50))
    changed = experiment_service.create_experiment(_definition(["gsm8k"], limit=100))
    assert len(changed.jobs) == 1
    assert changed.__dict__["skipped_items"] == []
