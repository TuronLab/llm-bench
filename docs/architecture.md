---
title: Architecture and execution model
permalink: /architecture/
---

# Architecture and execution model

## The two meanings of “backend”

The **application backend** is `apps/api/`: a FastAPI service that exposes the REST API and coordinates experiments. A **provider backend** is the server that generates tokens for a model, such as vLLM or Ollama. Providers are adapters in `infrastructure/providers/`; they are not the web API.

```text
CLI or web UI → API application → provider → model
                         |
                         `→ scheduler → lm-evaluation-harness → JSON results/logs
```

The CLI is available as the native `llm-bench` command or as the Compose `cli` container. Both are thin clients of the API application: neither starts providers nor runs benchmarks directly.

## What happens when an experiment runs

1. The API validates and persists an experiment definition.
2. It creates one job for each model and benchmark combination.
3. It constructs the selected provider from the registry.
4. The provider starts a Docker container, or connects to an existing remote service.
5. Once healthy, the runner invokes `lm_eval` for each job.
6. Results and logs are persisted; the provider is stopped unless `keep_alive` is enabled.

vLLM and llama.cpp serve one selected model per process, so the API starts a fresh instance for each model. Ollama and OpenAI-compatible APIs can be reused across the models in an experiment.

## Scheduling and failures

`core/scheduler/` supports sequential and bounded parallel execution. It locks a provider instance unless that provider declares `supports_concurrency: true`, preventing a single GPU server from being assigned conflicting benchmark jobs.

Failure isolation is intentional: a failed job does not prevent later jobs from running; a vLLM or llama.cpp startup failure marks only that model's jobs as failed. An experiment is considered completed when at least one job succeeds.

## Persistence

`infrastructure/storage/` is the persistence boundary. Its current implementation writes JSON files under `experiments/` and `results/`, with job logs under `logs/`. Replacing that storage with a database should not require changing the scheduler, runner, or providers.

## Extending a provider

Implement the `Provider` interface in `infrastructure/providers/`, register it in `registry.py`, and expose its configuration fields in `apps/api/app/api/routes/providers.py`. The scheduler and runner only depend on the shared provider interface.
