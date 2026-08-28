# LLM Benchmarking Framework

Self-hosted framework for evaluating LLM deployments across inference backends.

It orchestrates inference providers, runs [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)—an open-source tool for running LLM benchmarks locally—and persists experiment definitions, execution logs, raw harness output, and metrics. The same workflow is available through a REST API, CLI, and web dashboard. Docker images install Python dependencies with [uv](https://docs.astral.sh/uv/) for faster, cached builds.

The project is intended for controlled comparisons that public leaderboards do not always cover: model revisions, quantized variants, and configurations deployed on your own hardware. It supports vLLM, Ollama, llama.cpp/GGUF, and existing OpenAI-compatible APIs.

## Quick start

To use `llm-bench`, start `backend`, which runs evaluations, and `frontend`, the browser dashboard for creating comparisons, tracking progress, and reviewing scores.

```bash
docker compose up -d --build backend frontend
docker compose run --build --rm cli experiment run experiments/examples/quickstart.yaml
```

This starts the API and dashboard, downloads the two small Ollama models in the example, and runs a short comparison. Open the dashboard at `http://localhost:3000`.

You can run the same experiment with the native `llm-bench` command after installing it; see the next section.

The quickstart evaluates two small models on a limited sample. For a real comparison, copy the template and give both candidates the same benchmark list and harness options:

```bash
cp infrastructure/templates/experiment_template.yaml experiments/my-comparison.yaml
docker compose run --rm cli experiment validate experiments/my-comparison.yaml
docker compose run --rm cli experiment run experiments/my-comparison.yaml
```

A minimal experiment definition looks like this:

```yaml
name: simple-ollama-test

providers:
  - type: ollama
    options:
      manage: false
      host: host.docker.internal
      port: 11434

models:
  - llama3.2:1b

benchmarks:
  - gsm8k

load_testing:
  concurrent_users: [1, 2, 4]
  input: "Tell me a short story about a robot."
  max_output_tokens: 64
  requests_per_user: 5
```

Alternatively, you can use the dashboard's **New Experiment** screen if you prefer not to edit YAML.

> **Note:** Docker Engine 24+ and Docker Compose v2 are required. The default
> installation and quickstart are CPU-only; install the NVIDIA Container Toolkit
> only if you explicitly enable GPU-backed providers.

## CLI installation and use

The CLI is a client of the API service: it creates experiments and displays status, results, and logs.

### Native terminal

Install the native command from the repository root:

```bash
uv tool install .
export BENCHLAB_API_URL=http://localhost:8000/api/v1
llm-bench experiment run experiments/examples/quickstart.yaml
```

Use `uv tool install --editable .` while developing. The API must already be running; for a local API without Compose, run `uv sync --group api` followed by `uv run --group api uvicorn apps.api.app.main:app --reload`.

### Docker Compose

Start the API service and run the same CLI in its container:

```bash
docker compose up -d backend
docker compose run --rm cli experiment run experiments/examples/quickstart.yaml
```

Managed vLLM, Ollama, and llama.cpp providers require Docker. Hugging Face runs
locally through Transformers and does not start a provider container. For a fully
external setup, use `openai_compatible` or Ollama with `manage: false`.

### macOS and Apple Silicon

Macs use Apple's Metal GPU, not NVIDIA CUDA. Ollama uses Metal when it runs
directly on macOS, but Docker Desktop containers normally run CPU-only. To use
the Mac GPU, install Ollama on macOS, start it there, and configure the provider
as externally managed:

```yaml
provider:
  type: ollama
  options:
    manage: false
    host: host.docker.internal  # backend in Docker Desktop
    port: 11434
```

If the backend also runs natively on macOS, use `host: localhost` instead.
The benchmark backend can remain in Docker; only the Ollama model server needs
to run natively to access Metal.


## Comparing model variants fairly

An experiment can evaluate benchmark quality, measure serving performance under load, or do both. To make a meaningful comparison between model variants, keep the relevant inputs identical:

- for benchmarks: the task list and `extra_harness_args` (especially `limit`, `num_fewshot`, and batch size);
- for load tests: the prompt, output-token limit, request rate/concurrency levels, and timeout settings;
- for both: the provider and prompting/API mode where possible, as well as the model revision, quantization, and serving settings recorded in the experiment definition.

The framework records benchmark scores, execution duration, and load-test metrics such as latency and throughput. A model identifier alone is not always enough to describe a variant, so put the exact Hugging Face revision, Ollama tag, or GGUF filename in the experiment and retain the YAML with the result.

See [providers and experiment definitions](docs/providers.md) for concrete vLLM, Ollama, llama.cpp, and remote-API examples.


### Benchmarks

Benchmark availability comes directly from the installed `lm-evaluation-harness` version, so it can include its full task registry and custom tasks. Get the exact list available in your deployment with:

```bash
docker compose run --rm cli benchmarks list
```

The bundled common-task catalogue, with a short description of each task, is in [supported benchmarks](docs/benchmarks.md). It is intentionally separate from the version-specific list returned by the command above.

### Load testing

Load tests measure serving performance under concurrent requests. An experiment can
run the same test at several concurrency levels and record latency, time to first
token, output speed, throughput, and errors for every model and provider.

Configure them with the `load_testing` section in an experiment definition. The
`input` can contain prompt text directly or point to a UTF-8 Markdown/text file:

```yaml
load_testing:
  concurrent_users: [1, 2, 4, 8]
  input: "file://./experiments/inputs/load-testing-long-prompt.md"
  max_output_tokens: 128
  requests_per_user: 2
```

See [load testing](docs/load_testing.md) for the full configuration, metrics, and
interpretation guidelines.

## How it works

```text
Web dashboard or `bench` CLI
              |
              v
        FastAPI application
              |
              +-- starts/reuses a provider (vLLM, Ollama, llama.cpp, remote API)
              +-- schedules benchmark and load-test jobs per model × provider
              +-- runs lm-evaluation-harness and load tests
              `-- stores results and logs
```

Provider containers are created on demand by the API, not declared as permanent Compose services. They are stopped after an experiment unless `keep_alive: true` is set. A failed model or benchmark does not stop the remaining jobs.

For the lifecycle, concurrency rules, and the distinction between the application backend and a model-serving backend, read [architecture](docs/architecture.md).

## Repository layout

```text
apps/                 Things a person uses
  api/                FastAPI API and experiment workflow
  cli/                `bench` command-line client
  web/                React dashboard
core/                 Provider-independent execution
  runner/             lm-evaluation-harness invocation and result parsing
  scheduler/          Job ordering, parallelism, and failure isolation
infrastructure/       Adapters and operational assets
  providers/          vLLM, Ollama, llama.cpp, OpenAI-compatible adapters
  storage/            Pluggable JSON/SQLite persistence and shared data models
  configs/            Provider option templates
  docker/             Dockerfiles and nginx configuration
  templates/          Experiment template
experiments/          Example definitions and persisted experiment records
results/              Persisted results
  benchmarks/         Persisted benchmark results
  load_testing/       Persisted load-test results
logs/                 Per-job logs
tests/                Scheduler and experiment regression tests
```

## Everyday commands

```bash
# Inspect provider types and harness tasks.
llm-bench providers list
llm-bench benchmarks list

# Create, run, inspect, or cancel an experiment.
llm-bench experiment create experiments/my-comparison.yaml
llm-bench experiment run <experiment-id>
llm-bench experiment status <experiment-id>
llm-bench experiment logs <experiment-id> <job-id>
llm-bench experiment cancel <experiment-id>

# Inspect persisted results.
llm-bench results list
llm-bench results show <model>
```

The CLI is a REST client: it expects an API service at `BENCHLAB_API_URL` (default: `http://localhost:8000/api/v1`). The web interface offers the same core workflow. Interactive API documentation is at `http://localhost:8000/docs`.

## Data and configuration

BenchLab supports two persistence backends, selectable with
`BENCHLAB_PERSISTENCE`:

- `json` (default): readable files on disk, compatible with existing data.
- `sqlite`: one local database file containing experiments and all results.

For JSON explicitly:

```bash
export BENCHLAB_PERSISTENCE=json
```

The JSON layout is:

```text
experiments/<id>.json                 experiment definition, jobs, and status
results/benchmarks/<model>.json       benchmark result history per model
results/load_testing/<model>.json     load-testing result history per model
logs/<experiment>/<job>.log           lm-evaluation-harness output
```

To store experiment state plus benchmark and load-testing results in one local
SQLite file, start the backend with:

```bash
export BENCHLAB_PERSISTENCE=sqlite
# Optional; defaults to results/benchlab.db
export BENCHLAB_SQLITE_PATH=/data/benchlab.db
```

With Docker Compose, exporting `BENCHLAB_PERSISTENCE=sqlite` before `docker
compose up` selects the same backend; the database is then persisted in the
host `results/` directory.

The REST API, CLI, and web interface use the same persistence contract, so no
interface changes are needed. JSON remains the default and is not migrated or
deleted automatically when SQLite is selected; this makes rollback safe. Path
overrides also include `BENCHLAB_EXPERIMENTS_DIR`, `BENCHLAB_RESULTS_DIR`, and
`BENCHLAB_LOGS_DIR`. Docker Compose sets these paths for the containers.
Provider option templates live in [`infrastructure/configs/providers/`](infrastructure/configs/providers/).

## Further reading

- [Architecture and execution model](docs/architecture.md)
- [Providers and experiment definitions](docs/providers.md)
- [Load testing metrics and request execution](docs/load_testing.md)
- [Supported benchmarks](docs/benchmarks.md)
- [Experiment template](infrastructure/templates/experiment_template.yaml)
- [Quickstart experiment](experiments/examples/quickstart.yaml)

## Development

```bash
uv sync --group api
export BENCHLAB_ROOT=$(pwd)
uv run --group api uvicorn apps.api.app.main:app --reload
```

For the web application, run `npm install && npm run dev` from `apps/web/`. Provider containers still require Docker because the API manages them through the Docker socket.
