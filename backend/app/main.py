"""
FastAPI application entrypoint for the LLM Benchmarking Framework backend.

Run directly with `uvicorn backend.app.main:app` or via the provided Docker
container (see docker/backend.Dockerfile and docker-compose.yml).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import benchmarks, experiments, providers, results
from backend.app.core.config import settings
from backend.app.core.logging import configure_logging
from storage.paths import ensure_directories

configure_logging()
ensure_directories()

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
