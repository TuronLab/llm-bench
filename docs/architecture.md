# Architecture and execution model

The **application backend** is `apps/api/`: a FastAPI service that exposes the REST API and coordinates experiments. Providers are adapters in `infrastructure/providers/`; they connect the application to model-serving systems such as vLLM, Ollama, llama.cpp, local Transformers, or an OpenAI-compatible API.

```text
CLI or web UI → API application → provider → model
                         |
                         `→ scheduler → benchmark/load-test runners → results and logs
```

The CLI is available as the native `llm-bench` command or as the Compose `cli` container. Both are thin clients of the API application: neither starts providers nor runs experiments directly.

## What happens when an experiment runs

1. The API validates and persists an **experiment definition**.
2. It creates one job for each provider/model/benchmark combination and, when configured, each provider/model/concurrency-level combination for load testing.
3. For each configured provider, it constructs an instance from the registry.
4. The provider starts a Docker container, loads a local model, or connects to an existing remote service.
5. Once ready, the appropriate runner executes either `lm_eval` benchmarks or **concurrent streaming load tests**.
6. Results, experiment state, and logs are persisted; managed providers are stopped unless `keep_alive` is enabled.

vLLM and llama.cpp serve one selected model per process, so the API starts a fresh instance for each model. Ollama and OpenAI-compatible APIs can be reused across the models in an experiment. When multiple providers are configured, the complete experiment matrix is executed for each provider.

## Scheduling and failures

`core/scheduler/` supports sequential and bounded parallel execution. It locks a provider instance unless that provider declares `supports_concurrency: true`, preventing a single server from being assigned conflicting jobs. Load tests intentionally use that provider instance to issue concurrent requests when measuring concurrency.

Failure isolation is intentional: a failed job does not prevent later jobs from running; a vLLM or llama.cpp startup failure marks only that model's jobs as failed. An experiment is considered completed when at least one job succeeds.

## Persistence

`infrastructure/storage/` is the persistence boundary. The default backend writes experiment definitions and results as **JSON files** under `experiments/` and `results/`, with job logs under `logs/`. The optional **SQLite backend** stores experiment state, benchmark results, and load-test results in a single database file. Both backends implement the same storage contracts, so the scheduler, runners, and providers do not depend on the selected format.

## Extending a provider

Implement the `Provider` interface in `infrastructure/providers/`, register it in `registry.py`, and expose its configuration fields in `apps/api/app/api/routes/providers.py`. The scheduler and runner only depend on the shared provider interface.
