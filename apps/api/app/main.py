"""
FastAPI application entrypoint for the LLM Benchmarking Framework API.

Run directly with `uvicorn apps.api.app.main:app` or via the provided Docker
container (see infrastructure/docker/backend.Dockerfile and docker-compose.yml).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.api.routes import benchmarks, experiments, providers, results
from apps.api.app.core.config import settings
from apps.api.app.core.logging import configure_logging
from apps.api.app.services.experiment_service import recover_interrupted_experiments
from infrastructure.storage.paths import ensure_directories

configure_logging()
ensure_directories()
recover_interrupted_experiments()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "REST API for orchestrating LLM benchmarking experiments across "
        "multiple inference providers using lm-evaluation-harness."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(providers.router, prefix=settings.API_V1_PREFIX)
app.include_router(benchmarks.router, prefix=settings.API_V1_PREFIX)
app.include_router(experiments.router, prefix=settings.API_V1_PREFIX)
app.include_router(results.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
