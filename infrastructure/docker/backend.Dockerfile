# syntax=docker/dockerfile:1
# API service (`apps/api`): FastAPI orchestration API + benchmark runner.
#
# This image bundles lm-evaluation-harness and the Docker CLI/SDK so the
# API service can both (a) execute `lm_eval` against provider endpoints and
# (b) launch/stop provider containers on the host's Docker daemon (mounted
# in via docker-compose.yml as a bind-mounted socket).
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BENCHLAB_ROOT=/app \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --group api

# Application code: API, execution core, and infrastructure adapters.
COPY apps /app/apps
COPY core /app/core
COPY infrastructure /app/infrastructure

EXPOSE 8000

CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
