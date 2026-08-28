"""
Core data models shared by the API application, execution core, and CLI.
Centralizing them in infrastructure keeps the other layers independent and
avoids circular imports.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, model_validator


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class ExecutionMode(str, enum.Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    STARTING_PROVIDER = "starting_provider"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperimentStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionConfig(BaseModel):
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    workers: int = Field(default=1, ge=1, description="Parallel workers, ignored in sequential mode")


class ProviderSpec(BaseModel):
    """The provider + its instance configuration, as declared in an experiment."""

    type: str = Field(..., description="Provider type, e.g. 'vllm', 'ollama', 'llamacpp', 'openai_compatible'")
    name: Optional[str] = Field(default=None, description="Instance name; defaults to the type if omitted")
    options: dict[str, Any] = Field(default_factory=dict)
    keep_alive: bool = False
    supports_concurrency: bool = False


class LoadTestingConfig(BaseModel):
    """Load-test settings. Each entry in ``concurrent_users`` becomes one job per model."""

    concurrent_users: list[Annotated[int, Field(ge=1)]] = Field(..., min_length=1, description="Concurrent users to test")
    input: str = Field(..., min_length=1, description="Prompt text or file:// URI to a UTF-8 .txt/.md file")
    max_output_tokens: int = Field(default=128, ge=1)
    requests_per_user: int = Field(default=1, ge=1)
    temperature: float = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=120, gt=0)


class ExperimentDefinition(BaseModel):
    """The declarative, user-authored description of an experiment (maps 1:1 to the YAML format)."""

    name: str
    description: Optional[str] = None
    providers: list[ProviderSpec] = Field(default_factory=list, min_length=1)
    # Accepted only for backwards compatibility with definitions created
    # before providers became a list. New YAML should use `providers`.
    provider: Optional[ProviderSpec] = Field(default=None, exclude=True)
    models: list[str]
    benchmarks: list[str] = Field(default_factory=list)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    extra_harness_args: dict[str, Any] = Field(default_factory=dict)
    load_testing: Optional[LoadTestingConfig] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_provider(cls, values: Any) -> Any:
        if isinstance(values, dict) and not values.get("providers") and values.get("provider"):
            values = dict(values)
            values["providers"] = [values["provider"]]
        return values

    @model_validator(mode="after")
    def set_legacy_provider(self) -> "ExperimentDefinition":
        if self.provider is None:
            self.provider = self.providers[0]
        names = [provider.name or provider.type for provider in self.providers]
        if len(names) != len(set(names)):
            raise ValueError("Provider names must be unique within an experiment")
        return self


class JobRecord(BaseModel):
    """One (model, benchmark) unit of work within an experiment."""

    id: str = Field(default_factory=_new_id)
    experiment_id: str
    provider_name: str
    model: str
    benchmark: str
    kind: str = "benchmark"
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    result_path: Optional[str] = None
    log_path: Optional[str] = None
    progress: Optional[float] = Field(default=None, description="0-100 estimate if available")


class ExperimentRecord(BaseModel):
    """Persisted, runtime state of an experiment: definition + derived jobs + status."""

    id: str = Field(default_factory=_new_id)
    definition: ExperimentDefinition
    status: ExperimentStatus = ExperimentStatus.DRAFT
    jobs: list[JobRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for job in self.jobs:
            counts[job.status.value] = counts.get(job.status.value, 0) + 1
        return {
            "id": self.id,
            "name": self.definition.name,
            "status": self.status.value,
            "total_jobs": len(self.jobs),
            "job_counts": counts,
        }


class ResultMetadata(BaseModel):
    model: str
    provider: str
    benchmark: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_seconds: Optional[float] = None
    harness_version: Optional[str] = None
    git_commit: Optional[str] = None
    execution_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkResult(BaseModel):
    """One stored result: metadata + the raw metrics produced by lm-evaluation-harness."""

    metadata: ResultMetadata
    metrics: dict[str, Any] = Field(default_factory=dict)
    raw: Optional[dict[str, Any]] = Field(default=None, description="Full, untouched harness output")


class LoadTestingResult(BaseModel):
    """One load-test measurement for a model/provider/concurrency level."""

    model: str
    provider: str
    concurrent_users: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    input: str
    prompt: str = ""
    input_filename: Optional[str] = None
    max_output_tokens: int
    requests_per_user: int
    provider_options: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
