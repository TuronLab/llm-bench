"""
Experiment orchestration service.

This is where the end-to-end workflow described in the project spec is
implemented:

    1. Launch the required provider container.
    2. Wait until the server is ready.
    3. Execute lm-evaluation-harness for every (model, benchmark) pair.
    4. Store the results.
    5. Stop the provider container (unless `keep_alive` is set).
    6. Continue with the next task.

Fault isolation
----------------
A single broken model or benchmark must never take down the rest of the
experiment. Three layers enforce this:

  * Job-level: the `Scheduler` already wraps every individual (model,
    benchmark) job in a try/except -- a job that raises is marked FAILED and
    the scheduler moves on to the next job (see core/scheduler/scheduler.py).

  * Model-level: some providers (vLLM, llama.cpp) can only serve a single
    model per running instance, so the framework starts/stops a fresh
    provider instance *per model* for those. If launching the provider for
    model X fails (bad checkpoint, OOM, port conflict, ...), only model X's
    jobs are marked FAILED with the captured error; the loop continues to
    the next model with a clean provider instance. Providers that can serve
    several models from one running instance (Ollama, OpenAI-compatible
    APIs) are started once and reused across all models.

  * Experiment-level: the entire run is additionally wrapped in a top-level
    try/except as a last-resort safety net, so an unexpected bug can never
    leave an experiment stuck in RUNNING forever -- it will always end up
    FAILED with a recorded error instead of silently dying in its thread.

The service builds `ScheduledJob`s from an `ExperimentDefinition` and hands
them to the `Scheduler`, which enforces sequential/parallel semantics and
per-provider concurrency safety. Job and experiment status transitions are
persisted immediately so the live monitoring page (which polls the REST
API) and API service restarts both see consistent state.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from infrastructure.providers.base import Provider, ProviderConfig, ProviderError
from infrastructure.providers.registry import create_provider
from core.runner.harness_runner import run_benchmark
from core.runner.load_testing_runner import run_load_testing_test
from core.scheduler.job import ScheduledJob
from core.scheduler.scheduler import Scheduler
from infrastructure.storage.experiment_store import experiment_store
from infrastructure.storage.result_store import result_store
from infrastructure.storage.load_testing_store import load_testing_store
from infrastructure.storage.schemas import (
    ExperimentDefinition,
    ExperimentRecord,
    ExperimentStatus,
    JobRecord,
    JobStatus,
)

logger = logging.getLogger("benchlab.services.experiments")

# Provider types that can only serve one model per running instance. For
# these, the framework must cycle the provider per model. Providers not in
# this set (ollama, openai_compatible) are assumed capable of serving
# whichever model each request asks for from a single running instance.
SINGLE_MODEL_PROVIDER_TYPES = {"vllm", "llamacpp"}

# Maps a provider type to the option key that carries "which model to serve"
# for single-model providers, so the service knows which key to override
# per model in the loop below.
_MODEL_OPTION_KEY = {
    "vllm": "model",
    "llamacpp": "model_path",
}

# Tracks the in-memory Scheduler for each currently-running experiment so
# `cancel_experiment` can signal it. Experiment *history* still lives on
# disk via `experiment_store`; this is purely a runtime index.
_active_schedulers: dict[str, Scheduler] = {}
_active_lock = threading.Lock()


def recover_interrupted_experiments() -> int:
    """Mark persisted executions as failed after an unexpected process stop."""
    recovered = 0
    for record in experiment_store.list_all():
        if record.status not in (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING):
            continue
        for job in record.jobs:
            if job.status in (JobStatus.PENDING, JobStatus.STARTING_PROVIDER, JobStatus.RUNNING):
                job.status = JobStatus.FAILED
                job.error = "Execution interrupted because the API process stopped unexpectedly."
                job.finished_at = datetime.utcnow()
        record.status = ExperimentStatus.FAILED
        record.updated_at = datetime.utcnow()
        experiment_store.save(record)
        recovered += 1
        logger.warning("Recovered interrupted experiment %s as failed", record.id)
    return recovered


def create_experiment(definition: ExperimentDefinition) -> ExperimentRecord:
    jobs = [
        JobRecord(
            experiment_id="",  # filled in below once we know the experiment id
            provider_name=provider_name,
            model=model,
            benchmark=benchmark,
        )
        for provider in definition.providers
        for model in definition.models
        for benchmark in definition.benchmarks
        for provider_name in [provider.name or provider.type]
    ]
    if definition.load_testing:
        jobs.extend(
            JobRecord(
                experiment_id="",
                provider_name=provider_name,
                model=model,
                benchmark=f"load_testing-{concurrent_users}",
                kind="load_testing",
            )
            for provider in definition.providers
            for model in definition.models
            for concurrent_users in definition.load_testing.concurrent_users
            for provider_name in [provider.name or provider.type]
        )
    record = ExperimentRecord(definition=definition, status=ExperimentStatus.DRAFT, jobs=jobs)
    for job in record.jobs:
        job.experiment_id = record.id
    experiment_store.save(record)
    logger.info("Created experiment %s (%s) with %d jobs", record.id, definition.name, len(jobs))
    return record


def get_experiment(experiment_id: str) -> Optional[ExperimentRecord]:
    return experiment_store.get(experiment_id)


def list_experiments() -> list[ExperimentRecord]:
    return experiment_store.list_all()


def cancel_experiment(experiment_id: str) -> bool:
    with _active_lock:
        scheduler = _active_schedulers.get(experiment_id)
    if scheduler:
        scheduler.cancel()
    record = experiment_store.get(experiment_id)
    if record and record.status in (ExperimentStatus.RUNNING, ExperimentStatus.QUEUED):
        record.status = ExperimentStatus.CANCELLED
        record.updated_at = datetime.utcnow()
        experiment_store.save(record)
        return True
    return False


def run_experiment_background(experiment_id: str) -> None:
    """Kick off experiment execution on a background thread and return immediately."""
    thread = threading.Thread(target=_run_experiment_safe, args=(experiment_id,), daemon=True)
    thread.start()


def _run_experiment_safe(experiment_id: str) -> None:
    """
    Top-level safety net: whatever happens inside `_run_experiment`, this
    thread must never die silently and leave an experiment stuck in
    RUNNING. Anything unexpected that escapes the per-model handling below
    is caught here, logged, and reflected as a FAILED experiment status.
    """
    try:
        _run_experiment(experiment_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error running experiment %s", experiment_id)
        record = experiment_store.get(experiment_id)
        if record is not None and record.status != ExperimentStatus.CANCELLED:
            _fail_remaining_jobs(record, f"Unexpected orchestration error: {exc}")
    finally:
        with _active_lock:
            _active_schedulers.pop(experiment_id, None)


def _run_experiment(experiment_id: str) -> None:
    record = experiment_store.get(experiment_id)
    if record is None:
        logger.error("Cannot run unknown experiment %s", experiment_id)
        return

    record.status = ExperimentStatus.RUNNING
    record.started_at = datetime.utcnow()
    record.updated_at = datetime.utcnow()
    experiment_store.save(record)

    definition = record.definition
    for provider_spec in definition.providers:
        provider_name = provider_spec.name or provider_spec.type
        provider_type = provider_spec.type
        if provider_type in SINGLE_MODEL_PROVIDER_TYPES:
            _run_single_model_provider_experiment(experiment_id, record, definition, provider_name, provider_type, provider_spec)
        else:
            _run_shared_provider_experiment(experiment_id, record, definition, provider_name, provider_type, provider_spec)

    _finalize_experiment_status(experiment_id)


def _run_shared_provider_experiment(
    experiment_id: str,
    record: ExperimentRecord,
    definition: ExperimentDefinition,
    provider_name: str,
    provider_type: str,
    provider_spec,
) -> None:
    """One provider instance, started once, serving every model in the experiment."""
    provider_config = _build_provider_config(definition, provider_name, provider_type, provider_spec.options, provider_spec)

    try:
        provider = create_provider(provider_config)
        _start_provider(provider)
    except Exception as exc:  # noqa: BLE001 - intentionally broad: any provider failure
        # (ProviderError, a Docker SDK error, an httpx timeout, a bad config
        # KeyError, ...) must be isolated to this provider's jobs rather than
        # propagate and abort the whole experiment.
        logger.error("Provider failed to start for experiment %s: %s", experiment_id, exc)
        _fail_jobs_for_models(record, definition.models, str(exc), provider_name=provider_name)
        return

    scheduler = _new_scheduler(experiment_id, definition)
    jobs_for_provider = [j for j in record.jobs if j.status == JobStatus.PENDING and j.provider_name == provider_name]
    scheduled = [
        ScheduledJob(
            record=job,
            run=_make_job_runner(provider, job, definition),
            provider_key=provider_name,
            supports_concurrency=provider_config.supports_concurrency,
        )
        for job in jobs_for_provider
    ]
    try:
        scheduler.run_all(scheduled)
    finally:
        _stop_provider_if_needed(provider, provider_config)


def _run_single_model_provider_experiment(
    experiment_id: str,
    record: ExperimentRecord,
    definition: ExperimentDefinition,
    provider_name: str,
    provider_type: str,
    provider_spec,
) -> None:
    """
    Providers that can only serve one model per instance are cycled: start,
    run all benchmarks for that model, stop, move to the next model. A
    failure launching or running against one model's provider instance is
    isolated to that model's jobs and does NOT stop the experiment.
    """
    model_option_key = _MODEL_OPTION_KEY[provider_type]

    for model in definition.models:
        record = experiment_store.get(experiment_id)  # refresh in case of concurrent cancel
        if record is None or record.status == ExperimentStatus.CANCELLED:
            logger.info("Experiment %s cancelled; stopping model loop", experiment_id)
            return

        model_jobs = [j for j in record.jobs if j.model == model and j.status == JobStatus.PENDING]
        if not model_jobs:
            continue

        options = dict(provider_spec.options)
        options[model_option_key] = model
        provider_config = _build_provider_config(definition, provider_name, provider_type, options, provider_spec)

        try:
            provider = create_provider(provider_config)
            _start_provider(provider)
        except Exception as exc:  # noqa: BLE001 - intentionally broad: any provider failure
            # (ProviderError, a Docker SDK error, an httpx timeout, a bad config
            # KeyError, an OOM signal surfaced as a generic RuntimeError, ...)
            # must be isolated to THIS model's jobs only. Narrowing this catch
            # to specific exception types would let an unanticipated failure
            # mode escape to the top-level safety net, which fails every
            # remaining job in the experiment -- exactly what per-model
            # isolation exists to prevent.
            logger.error(
                "Provider failed to start for model '%s' in experiment %s: %s. "
                "Skipping this model and continuing with the rest.",
                model, experiment_id, exc,
            )
            _fail_jobs_for_models(record, [model], str(exc))
            continue  # <-- the key behavior: move on to the next model

        scheduler = _new_scheduler(experiment_id, definition)
        scheduled = [
            ScheduledJob(
                record=job,
                run=_make_job_runner(provider, job, definition),
                provider_key=f"{provider_name}:{model}",
                supports_concurrency=provider_config.supports_concurrency,
            )
            for job in model_jobs
        ]
        try:
            scheduler.run_all(scheduled)
        except Exception as exc:  # noqa: BLE001
            # Defense in depth: the scheduler already isolates per-job
            # failures, but if something still escapes, don't let it take
            # down the remaining models either.
            logger.exception(
                "Unexpected error while benchmarking model '%s' in experiment %s; "
                "continuing with remaining models.", model, experiment_id,
            )
            _fail_jobs_for_models(record, [model], str(exc), only_pending=True)
        finally:
            _stop_provider_if_needed(provider, provider_config)


def _build_provider_config(
    definition: ExperimentDefinition, provider_name: str, provider_type: str, options: dict, provider_spec
) -> ProviderConfig:
    return ProviderConfig(
        name=provider_name,
        type=provider_type,
        options=options,
        keep_alive=provider_spec.keep_alive,
        supports_concurrency=provider_spec.supports_concurrency,
    )


def _new_scheduler(experiment_id: str, definition: ExperimentDefinition) -> Scheduler:
    scheduler = Scheduler(
        mode=definition.execution.mode,
        workers=definition.execution.workers,
        on_status_change=lambda job, status, error: _on_job_status_change(
            experiment_id, job.record.id, status, error
        ),
    )
    with _active_lock:
        _active_schedulers[experiment_id] = scheduler
    return scheduler


def _stop_provider_if_needed(provider: Provider, provider_config: ProviderConfig) -> None:
    if provider_config.keep_alive:
        return
    try:
        provider.stop()
    except Exception:  # noqa: BLE001
        logger.exception("Error stopping provider '%s'", provider_config.name)


def _start_provider(provider: Provider) -> None:
    logger.info("Starting provider '%s'", provider.config.name)
    provider.start()
    logger.info("Provider '%s' started; waiting for readiness", provider.config.name)
    provider.wait_until_ready()
    logger.info("Provider '%s' is ready", provider.config.name)
    pull_configured_models = getattr(provider, "pull_configured_models", None)
    if callable(pull_configured_models):
        logger.info("Ensuring configured provider models are available")
        pull_configured_models()


def _make_job_runner(provider: Provider, job: JobRecord, definition: ExperimentDefinition):
    def _runner() -> None:
        if job.kind == "load_testing":
            if definition.load_testing is None:  # Defensive: persisted malformed job.
                raise RuntimeError("LoadTesting job is missing its configuration")
            concurrent_users = int(job.benchmark.removeprefix("load_testing-"))
            load_generation = definition.generation.model_dump(exclude_none=True)
            # Load-test-specific controls take precedence when explicitly
            # configured. Defaults are not considered an override.
            if "temperature" in definition.load_testing.model_fields_set:
                load_generation["temperature"] = definition.load_testing.temperature
            if "max_output_tokens" in definition.load_testing.model_fields_set:
                load_generation["max_tokens"] = definition.load_testing.max_output_tokens
            result = run_load_testing_test(
                provider=provider, model=job.model, config=definition.load_testing,
                concurrent_users=concurrent_users, generation=load_generation
            )
            path = load_testing_store.append(result)
            job.result_path = str(path)
            return
        benchmark_args = dict(definition.extra_harness_args)
        generation = definition.generation.model_dump(exclude_none=True)
        benchmark_args["gen_kw"] = {**generation, **benchmark_args.get("gen_kw", {})}
        result = run_benchmark(
            provider=provider,
            model=job.model,
            benchmark=job.benchmark,
            experiment_id=job.experiment_id,
            job_id=job.id,
            extra_args=benchmark_args,
        )
        path = result_store.append(result)
        job.result_path = str(path)

    return _runner


def _on_job_status_change(
    experiment_id: str, job_id: str, status: JobStatus, error: Optional[str]
) -> None:
    record = experiment_store.get(experiment_id)
    if record is None:
        return
    for job in record.jobs:
        if job.id != job_id:
            continue
        job.status = status
        if status == JobStatus.RUNNING:
            job.started_at = datetime.utcnow()
        if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            job.finished_at = datetime.utcnow()
        if error:
            job.error = error
        break
    record.updated_at = datetime.utcnow()
    experiment_store.save(record)


def _fail_jobs_for_models(
    record: ExperimentRecord, models: list[str], error: str, only_pending: bool = False,
    provider_name: str | None = None,
) -> None:
    """Mark every (still-pending) job for the given models as FAILED, without touching other models' jobs."""
    models_set = set(models)
    for job in record.jobs:
        if job.model not in models_set:
            continue
        if provider_name is not None and job.provider_name != provider_name:
            continue
        if only_pending and job.status != JobStatus.PENDING:
            continue
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            continue
        job.status = JobStatus.FAILED
        job.error = error
        job.finished_at = datetime.utcnow()
    record.updated_at = datetime.utcnow()
    experiment_store.save(record)


def _fail_remaining_jobs(record: ExperimentRecord, error: str) -> None:
    """Used only by the top-level safety net: fail whatever hasn't finished yet."""
    for job in record.jobs:
        if job.status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.STARTING_PROVIDER):
            job.status = JobStatus.FAILED
            job.error = error
            job.finished_at = datetime.utcnow()
    record.status = ExperimentStatus.FAILED
    record.updated_at = datetime.utcnow()
    experiment_store.save(record)


def _finalize_experiment_status(experiment_id: str) -> None:
    """
    Compute the overall experiment status from its jobs' final states. An
    experiment is COMPLETED as long as at least one job succeeded or all
    jobs were cleanly skipped -- partial success is still a completed run,
    not a failed one, since that's the whole point of the per-model/per-job
    isolation: individual breakage doesn't abort the run. Only a run where
    every single job failed is reported as an overall FAILED experiment.
    """
    record = experiment_store.get(experiment_id)
    if record is None or record.status == ExperimentStatus.CANCELLED:
        return
    statuses = [j.status for j in record.jobs]
    if not statuses:
        record.status = ExperimentStatus.COMPLETED
    elif all(s == JobStatus.FAILED for s in statuses):
        record.status = ExperimentStatus.FAILED
    else:
        record.status = ExperimentStatus.COMPLETED
    record.updated_at = datetime.utcnow()
    experiment_store.save(record)
