# syntax=docker/dockerfile:1
# CLI service: `bench` command, invoked via `docker compose run cli ...`.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BENCHLAB_ROOT=/app \
    BENCHLAB_API_URL=http://backend:8000/api/v1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY apps/cli/requirements.txt /app/apps/cli/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r /app/apps/cli/requirements.txt

COPY apps /app/apps
COPY infrastructure /app/infrastructure
COPY experiments /app/experiments

ENTRYPOINT ["python", "-m", "apps.cli.main"]
CMD ["--help"]
