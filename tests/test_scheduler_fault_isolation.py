"""
Lightweight sanity tests for the scheduler's fault-isolation behavior.

These don't require Docker, a running API service, or lm-evaluation-harness --
they exercise `Scheduler` directly with fake jobs to prove that one job
raising an exception never prevents the rest from running. Run with:

    pytest tests/test_scheduler_fault_isolation.py -v

or, without pytest installed, simply:

    python -m tests.test_scheduler_fault_isolation
"""

from __future__ import annotations

from core.scheduler.job import ScheduledJob
from core.scheduler.scheduler import Scheduler
from infrastructure.storage.schemas import ExecutionMode, JobRecord, JobStatus


def _make_job(model: str, benchmark: str, should_fail: bool, calls: list[str]):
    record = JobRecord(experiment_id="exp1", provider_name="p", model=model, benchmark=benchmark)

    def _run():
        calls.append(f"{model}:{benchmark}")
        if should_fail:
            raise RuntimeError(f"simulated failure for {model}/{benchmark}")

    return ScheduledJob(record=record, run=_run, provider_key="p", supports_concurrency=False)


def test_sequential_one_failure_does_not_stop_the_rest():
    calls: list[str] = []
    statuses: dict[str, JobStatus] = {}

    def on_status(job, status, error):
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            statuses[job.record.id] = status

    jobs = [
        _make_job("model-a", "mmlu", should_fail=True, calls=calls),
        _make_job("model-b", "mmlu", should_fail=False, calls=calls),
        _make_job("model-c", "mmlu", should_fail=False, calls=calls),
    ]
    scheduler = Scheduler(mode=ExecutionMode.SEQUENTIAL, on_status_change=on_status)
    scheduler.run_all(jobs)

    # All three jobs must have been attempted, despite the first one failing.
    assert calls == ["model-a:mmlu", "model-b:mmlu", "model-c:mmlu"]
    assert statuses[jobs[0].record.id] == JobStatus.FAILED
    assert statuses[jobs[1].record.id] == JobStatus.COMPLETED
    assert statuses[jobs[2].record.id] == JobStatus.COMPLETED


def test_parallel_one_failure_does_not_stop_the_rest():
    calls: list[str] = []
    statuses: dict[str, JobStatus] = {}

    def on_status(job, status, error):
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            statuses[job.record.id] = status

    jobs = [
        _make_job("model-a", "gsm8k", should_fail=False, calls=calls),
        _make_job("model-b", "gsm8k", should_fail=True, calls=calls),
        _make_job("model-c", "gsm8k", should_fail=False, calls=calls),
        _make_job("model-d", "gsm8k", should_fail=False, calls=calls),
    ]
    scheduler = Scheduler(mode=ExecutionMode.PARALLEL, workers=4, on_status_change=on_status)
    scheduler.run_all(jobs)

    assert len(calls) == 4
    assert statuses[jobs[1].record.id] == JobStatus.FAILED
    for i in (0, 2, 3):
        assert statuses[jobs[i].record.id] == JobStatus.COMPLETED


if __name__ == "__main__":
    test_sequential_one_failure_does_not_stop_the_rest()
    test_parallel_one_failure_does_not_stop_the_rest()
    print("All fault-isolation sanity tests passed.")
