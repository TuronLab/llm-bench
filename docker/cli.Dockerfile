# CLI service: `bench` command, invoked via `docker compose run cli ...`.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BENCHLAB_ROOT=/app \
    BENCHLAB_API_URL=http://backend:8000/api/v1

WORKDIR /app

COPY cli/requirements.txt /app/cli/requirements.txt
RUN pip install --no-cache-dir -r /app/cli/requirements.txt

COPY cli /app/cli
COPY storage /app/storage
COPY experiments /app/experiments

ENTRYPOINT ["python", "-m", "cli.main"]
CMD ["--help"]
