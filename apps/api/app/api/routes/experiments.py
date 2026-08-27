from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.api.app.services import experiment_service
from infrastructure.storage.paths import LOGS_DIR
from infrastructure.storage.schemas import ExperimentDefinition

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("")
def list_experiments():
    return {"experiments": [r.summary() for r in experiment_service.list_experiments()]}


@router.post("", status_code=201)
def create_experiment(definition: ExperimentDefinition):
    record = experiment_service.create_experiment(definition)
    return record


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str):
    record = experiment_service.get_experiment(experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    return record


@router.post("/{experiment_id}/run")
def run_experiment(experiment_id: str):
    record = experiment_service.get_experiment(experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    experiment_service.run_experiment_background(experiment_id)
    return {"status": "started", "experiment_id": experiment_id}


@router.post("/{experiment_id}/cancel")
def cancel_experiment(experiment_id: str):
    cancelled = experiment_service.cancel_experiment(experiment_id)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail="Experiment is not currently running or does not exist",
        )
    return {"status": "cancelled", "experiment_id": experiment_id}


@router.get("/{experiment_id}/logs/{job_id}")
def get_job_logs(experiment_id: str, job_id: str, tail: int = 500):
    log_path = LOGS_DIR / experiment_id / f"{job_id}.log"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="No logs found for this job yet")
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"lines": lines[-tail:]}
