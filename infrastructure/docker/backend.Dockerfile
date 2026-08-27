# Backend service: FastAPI orchestration API + benchmark runner.
#
# This image bundles lm-evaluation-harness and the Docker CLI/SDK so the
# backend can both (a) execute `lm_eval` against provider endpoints and
# (b) launch/stop provider containers on the host's Docker daemon (mounted
# in via docker-compose.yml as a bind-mounted socket).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BENCHLAB_ROOT=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/api/requirements.txt

# Application code: API, execution core, and infrastructure adapters.
COPY apps /app/apps
COPY core /app/core
COPY infrastructure /app/infrastructure
COPY tests /app/tests

EXPOSE 8000

CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
