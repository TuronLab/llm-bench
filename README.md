# LLM Benchmarking Framework

A Docker-native, backend-agnostic framework for benchmarking Large Language Models with
[lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness). It orchestrates
inference servers, runs the harness, stores results, and gives you a CLI and a web dashboard to
create, monitor, and review experiments — without ever installing a Python package, downloading a
model, or leaving a virtual environment on your host machine.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Docker Architecture](#docker-architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running Benchmarks](#running-benchmarks)
- [Creating Experiments](#creating-experiments)
- [Execution Modes & Fault Isolation](#execution-modes--fault-isolation)
- [CLI Reference](#cli-reference)
- [Web Interface Guide](#web-interface-guide)
- [Provider Configuration](#provider-configuration)
- [Adding New Providers](#adding-new-providers)
- [Adding New Benchmarks](#adding-new-benchmarks)
- [Result Format](#result-format)
- [REST API](#rest-api)
- [Development Setup](#development-setup)
- [Troubleshooting](#troubleshooting)
- [Frequently Asked Questions](#frequently-asked-questions)

---

## Project Overview

This framework answers one question repeatedly, cheaply, and reproducibly: **how does model X
perform on benchmark Y, served by backend Z?** It does this by:

1. Launching whatever inference server a model needs (vLLM, Ollama, llama.cpp, or pointing at a
   remote OpenAI-compatible API).
2. Waiting for that server to become healthy.
3. Invoking `lm-evaluation-harness` against it — the framework never reimplements evaluation logic,
   it only orchestrates the harness.
4. Persisting the results as JSON, accumulating history over time.
5. Tearing the provider back down (unless told to keep it alive).
6. Moving on to the next (model, benchmark) combination — and critically, **doing so even if the
   current one failed**. See [Execution Modes & Fault Isolation](#execution-modes--fault-isolation).

Everything runs in Docker. The only things that ever touch your host filesystem are:

```text
experiments/   # experiment definitions + run history (JSON)
results/       # one JSON file per model, accumulating over time
logs/          # optional per-job execution logs
```

Python packages, model weights, HuggingFace/Ollama caches, and temporary harness artifacts all
live inside container filesystems or ephemeral containers that are destroyed after use.

---

## Architecture

```text
                        ┌─────────────────────┐
                        │      Frontend        │  React SPA (dashboard, wizard,
                        │  (nginx + static)     │  live monitoring)
                        └──────────┬───────────┘
                                   │ /api (proxied)
                                   ▼
┌───────────┐   REST API   ┌─────────────────────┐        ┌────────────────────┐
│    CLI     │◄────────────►│      Backend         │──────► │  Provider container │
│  (`bench`) │              │  FastAPI + Scheduler  │  start/ │  (vLLM / Ollama /   │
└───────────┘              │  + Runner + Storage    │  stop  │  llama.cpp), or a   │
                            └──────────┬───────────┘        │  remote OpenAI API   │
                                       │                     └────────────────────┘
                     lm_eval subprocess│
                                       ▼
                            ┌─────────────────────┐
                            │ lm-evaluation-harness │
                            └─────────────────────┘
```

**Design principle: the benchmark engine never depends on a specific provider.** Every provider
implements the same `Provider` interface (`start`, `stop`, `wait_until_ready`, `list_models`,
`endpoint`). The scheduler and the harness runner only ever talk to that interface, so adding a
new backend never touches orchestration code (see [Adding New Providers](#adding-new-providers)).

### Repository layout

```text
apps/                         User-facing applications
├── api/                      FastAPI REST API and experiment workflow
├── cli/                      Typer-based `bench` REST client
└── web/                      React + Vite dashboard
core/                         Provider-independent execution logic
├── runner/                   Invokes lm-evaluation-harness and parses results
└── scheduler/                Schedules jobs and enforces concurrency safety
infrastructure/               External-system adapters and operational resources
├── providers/                vLLM, Ollama, llama.cpp, and OpenAI-compatible adapters
├── storage/                  Pydantic models and JSON-backed persistence
├── configs/                  Global defaults and provider option templates
├── docker/                   Dockerfiles, nginx configuration, provider assets
└── templates/                Reusable experiment and provider templates
experiments/                  Persisted experiment history and example YAMLs
results/                      Persisted benchmark results, one file per model
tests/                        Fault-isolation sanity tests
```

### Why the backend also runs the harness

The spec describes a "Benchmark Runner" as a conceptually separate responsibility from the
"Backend" API — and in this codebase it *is* separate at the package level: `core/runner/` contains no
FastAPI, HTTP, or scheduling code, only the logic to build and execute an `lm_eval` invocation and
parse its output. In this reference deployment, the backend container imports and calls that
package directly (in a background thread per experiment) since it already needs `lm-evaluation-harness`
installed to build harness commands and already holds the Docker socket needed to manage provider
containers. If you need to scale evaluation execution independently of the API (e.g. many
concurrent experiments across a fleet), the `core/runner/`, `core/scheduler/`, and `infrastructure/storage/` packages are
already decoupled from `apps/api/app` and can be lifted into a standalone worker service/container
communicating over a queue without changing their internals.

---

## Technology Stack

| Layer      | Technology |
|------------|------------|
| Backend    | Python 3.11, FastAPI, Pydantic v2, Uvicorn |
| Evaluation | lm-evaluation-harness (invoked as a subprocess, never reimplemented) |
| Scheduler  | Python `concurrent.futures` thread pool with per-provider locking |
| Providers  | Docker SDK for Python (container lifecycle), httpx (HTTP health checks / OpenAI-compatible calls) |
| CLI        | Typer + Rich (colored tables, progress bars) |
| Frontend   | React 18, Vite, React Router (no heavyweight UI framework — plain CSS) |
| Storage    | JSON files on disk (experiments/, results/) — no external database required |
| Containers | Docker Compose, nginx (static frontend + API proxy) |

---

## Docker Architecture

```text
docker-compose.yml
├── backend    → infrastructure/docker/backend.Dockerfile   (FastAPI + lm-eval + Docker SDK)
├── frontend   → infrastructure/docker/frontend.Dockerfile  (Vite build served by nginx)
└── cli        → infrastructure/docker/cli.Dockerfile       (one-shot `bench` invocations)
```

Provider containers (vLLM, Ollama, llama.cpp) are **not** declared as static `docker-compose`
services. They're launched dynamically by the backend via the Docker Engine API (mounted in via
`/var/run/docker.sock`) exactly when an experiment needs them, and destroyed immediately after
(unless `keep_alive: true` is set on the provider). This matches the requirement that provider
containers are ephemeral by default.

**Networking**: the backend talks to the host's Docker daemon over the mounted socket
("Docker-outside-of-Docker"). Because of that, provider containers are attached to the same
user-defined bridge network as the backend (`benchlab-network`) and are addressed by **container
name**, not `localhost` — `localhost` inside the backend container would never reach a sibling
container's published port. Each provider's `endpoint()` implementation reflects this (see
`infrastructure/providers/vllm_provider.py`, `infrastructure/providers/ollama_provider.py`, `infrastructure/providers/llamacpp_provider.py`).
Host port bindings are still published for convenience (e.g. `curl localhost:8000/v1/models` for
manual debugging), but backend↔provider traffic always goes over the internal network.

Persistent volumes (bind mounts, not named volumes, so paths are transparent):

```yaml
volumes:
  - ./experiments:/app/experiments
  - ./results:/app/results
  - ./logs:/app/logs
  - /var/run/docker.sock:/var/run/docker.sock   # backend only
```

---

## Installation

**Prerequisites**: Docker Engine 24+, Docker Compose v2, and (for GPU-backed providers)
the NVIDIA Container Toolkit.

```bash
git clone <this-repository-url> llm-benchmarking-framework
cd llm-benchmarking-framework

# Build every image (backend, frontend, cli)
docker compose build

# Start the backend + web dashboard
docker compose up -d backend frontend
```

The API is now reachable at `http://localhost:8000`, and the dashboard at `http://localhost:3000`.

No `pip install`, `npm install`, or Python virtual environment is required on your host — those
happen inside the `docker compose build` step, entirely within container filesystems.

---

## Quick Start

### 1. Run the bundled example with the CLI

```bash
docker compose run --rm cli experiment run experiments/examples/quickstart.yaml
```

This pulls two small Ollama models, runs them against `arc_easy` and `boolq` with a 50-example
sample (fast smoke test), and streams a live progress bar in your terminal.

### 2. Or use the web dashboard

1. Open `http://localhost:3000`.
2. Go to **New Experiment**.
3. Pick a provider (e.g. `ollama`), add one or two models, pick a couple of benchmarks, choose
   sequential or parallel execution, and click **Launch Experiment**.
4. You're redirected to **Live Monitoring**, which auto-refreshes progress, per-job status, and
   streams execution logs.
5. Once finished, open **Dashboard** to see the model × benchmark score matrix; click any cell for
   every metric the harness reported.

### 3. Check the results on disk

```bash
cat results/llama3.2_1b.json | jq '.[0].metrics'
```

---

## Configuration

Global defaults live in `infrastructure/configs/default.yaml`:

```yaml
storage:
  experiments_dir: experiments
  results_dir: results
  logs_dir: logs

execution:
  default_mode: sequential
  default_workers: 2
  provider_ready_timeout_seconds: 300
  provider_ready_poll_interval_seconds: 2

harness:
  default_args:
    num_fewshot: null
    batch_size: auto
```

Every path is overridable via environment variables (see `infrastructure/storage/paths.py`):

| Variable | Default | Purpose |
|---|---|---|
| `BENCHLAB_ROOT` | project root | Base path for relative resolution |
| `BENCHLAB_EXPERIMENTS_DIR` | `experiments/` | Where experiment JSON records are written |
| `BENCHLAB_RESULTS_DIR` | `results/` | Where result JSON files are written |
| `BENCHLAB_LOGS_DIR` | `logs/` | Where per-job execution logs are written |
| `BENCHLAB_DOCKER_NETWORK` | `benchlab-network` | Network provider containers join |
| `BENCHLAB_API_URL` | `http://localhost:8000/api/v1` | Used by the CLI to reach the backend |
| `BENCHLAB_CORS_ORIGINS` | `*` | Backend CORS allow-list |
| `BENCHLAB_LOG_LEVEL` | `INFO` | Backend log verbosity |

Provider-specific configuration schemas and defaults live in `infrastructure/configs/providers/*.yaml` — see
[Provider Configuration](#provider-configuration).

---

## Running Benchmarks

An experiment is the unit of work: a provider, a list of models, a list of benchmarks, and an
execution mode. Every `(model, benchmark)` pair becomes one job.

```bash
# Validate without submitting
docker compose run --rm cli experiment validate my-experiment.yaml

# Submit + run + stream progress
docker compose run --rm cli experiment run my-experiment.yaml

# Or split creation and execution
docker compose run --rm cli experiment create my-experiment.yaml
docker compose run --rm cli experiment run <experiment-id>
```

Each job's flow: **launch provider (if not already running for this batch) → wait for readiness →
run `lm_eval` → parse & store results → move to the next job → tear down the provider once the
batch for that provider instance is done** (see [Execution Modes & Fault Isolation](#execution-modes--fault-isolation)
for exactly how "batch" is defined per provider type).

---

## Creating Experiments

### Via YAML

```yaml
name: llama-vs-mistral
description: "Compare two 7-8B instruct models on core reasoning benchmarks."

provider:
  type: ollama
  options:
    manage: true
    pull_models: [llama3, mistral]

models:
  - llama3
  - mistral

benchmarks:
  - mmlu
  - gsm8k
  - truthfulqa_mc2

execution:
  mode: parallel
  workers: 2

extra_harness_args:
  num_fewshot: 5
```

Copy `infrastructure/templates/experiment_template.yaml` as a starting point, or see `experiments/examples/` for
two ready-to-run samples (`quickstart.yaml` for Ollama, `multi_provider.yaml` for vLLM).

### Via the CLI wizard

```bash
docker compose run --rm cli experiment create
```

Prompts you step by step (provider → provider options → models → benchmarks → execution mode) and
submits the resulting definition — no YAML file needed.

### Via the web UI

**Experiment Builder** walks through the same steps visually: Provider → Models → Benchmarks →
Execution → Review, showing only the configuration fields relevant to the provider you picked.

---

## Execution Modes & Fault Isolation

### Sequential vs. Parallel

- **Sequential** (`execution.mode: sequential`): jobs run strictly one after another.
- **Parallel** (`execution.mode: parallel`, `workers: N`): up to `N` jobs run concurrently. The
  scheduler (`core/scheduler/scheduler.py`) still serializes any two jobs that would hit the *same*
  provider instance unless that provider explicitly declares `supports_concurrency: true` — so a
  single-GPU vLLM/Ollama/llama.cpp instance is never double-booked, even in parallel mode.
  `supports_concurrency: true` makes sense for remote APIs (OpenAI, Azure, etc.) that can happily
  handle many simultaneous requests.

### A broken model or benchmark never stops the run

This is enforced at three layers, from narrowest to broadest:

1. **Job-level** — every individual `(model, benchmark)` job runs inside a try/except in the
   scheduler. If `lm_eval` exits non-zero or raises for any reason, that job is marked `FAILED`
   with the captured error, and the scheduler immediately continues with the next job — in both
   sequential and parallel mode.

2. **Model-level** — providers that can only serve one model per running instance (vLLM,
   llama.cpp) are restarted once per model in the experiment. If launching the provider for one
   model fails (bad checkpoint path, OOM, port conflict, ...), only that model's jobs are marked
   `FAILED`; the framework tears down the broken attempt and moves on to the *next model* with a
   fresh provider instance. Providers that can serve multiple models from a single running
   instance (Ollama, OpenAI-compatible APIs) are started once and reused, so this failure mode
   doesn't apply to them the same way — but any HTTP-level failure calling them still only fails
   the specific job, not the whole run.

3. **Experiment-level** — the entire orchestration routine runs inside a top-level safety-net
   try/except (`_run_experiment_safe` in `apps/api/app/services/experiment_service.py`). Anything
   truly unexpected that escapes the two layers above is caught, logged, and reflected as job/
   experiment failure instead of leaving an experiment silently stuck in `RUNNING` forever.

An experiment's overall status is `COMPLETED` as long as at least one job succeeded (partial
success is still a completed run — that's the entire point of this isolation); it's only reported
`FAILED` if *every* job in it failed.

This behavior is covered by two test files:

- `tests/test_scheduler_fault_isolation.py` — proves at the scheduler level, without needing
  Docker or a real model, that one failing job never prevents the rest from running, in both
  sequential and parallel mode.
- `tests/test_experiment_fault_isolation_e2e.py` — a full end-to-end regression test through the
  real REST API (create -> run -> poll) with a faked provider, guarding specifically against a bug
  found during development where a too-narrow `except` clause around provider startup let an
  unanticipated exception type escape and incorrectly fail every remaining model in the experiment
  instead of just the broken one.

```bash
docker compose run --rm backend python -m tests.test_scheduler_fault_isolation
docker compose run --rm backend python -m tests.test_experiment_fault_isolation_e2e
```

---

## CLI Reference

All commands are namespaced under `bench` (run as `docker compose run --rm cli <command>`, or
`python -m apps.cli.main <command>` if working outside Docker with `BENCHLAB_API_URL` set).

| Command | Description |
|---|---|
| `bench providers list` | List provider types and their configuration schema |
| `bench models list --provider ollama [--host H] [--port P] [--endpoint URL]` | List models available through a provider |
| `bench benchmarks list` | List every benchmark available via lm-evaluation-harness |
| `bench experiment create [file.yaml]` | Submit an experiment (interactive wizard if no file given) |
| `bench experiment validate file.yaml` | Validate an experiment YAML without submitting it |
| `bench experiment run <file.yaml \| experiment-id>` | Create (if a file) and run an experiment, streaming progress |
| `bench experiment status <experiment-id>` | Show current status and a per-job table |
| `bench experiment logs <experiment-id> <job-id> [--tail N]` | Show execution logs for one job |
| `bench experiment cancel <experiment-id>` | Cancel a running experiment |
| `bench experiment list` | List all known experiments |
| `bench results list` | Show the model × benchmark summary matrix |
| `bench results show <model>` | Show every stored result for a model |
| `bench dashboard` | Open the web dashboard in your browser |

---

## Web Interface Guide

- **Dashboard** — model × benchmark matrix of primary scores. Click any cell to open the detailed
  view with every metric the harness reported for that run (not just the primary one), with
  sorting and filtering.
- **Experiments** — every experiment ever created, sorted with actionable ones (running, queued,
  failed) first, with a live per-status job-count summary.
- **New Experiment** — the wizard: Provider → Models → Benchmarks → Execution → Review. Provider
  option fields are generated dynamically from the backend's provider schema, so you only ever see
  fields relevant to the provider you picked.
- **Live Monitoring** — pick a running (or historical) experiment; see current/pending/completed/
  failed job counts, the currently running (model, benchmark) pair, elapsed time, a progress bar,
  and a per-job table where clicking "Logs" streams that job's execution log, auto-refreshing.

---

## Provider Configuration

Each provider's configuration schema is also served live from `GET /api/v1/providers` (which is
what powers the web wizard's dynamic form), and templated in `infrastructure/configs/providers/*.yaml`.

### vLLM

| Option | Default | Notes |
|---|---|---|
| `model` | *required* | HF model id or local path. **One model per running instance.** |
| `port` | 8000 | |
| `tensor_parallel_size` | 1 | |
| `gpu_memory_utilization` | 0.9 | |
| `dtype` | `auto` | |
| `gpus` | true | Requests GPU devices for the container |
| `hf_token` | - | For gated HF models |
| `host_models_dir` | - | Bind-mount to persist the HF cache across runs |

### Ollama

| Option | Default | Notes |
|---|---|---|
| `manage` | true | `true`: launch a container. `false`: connect to an existing server via `host`/`port`. |
| `host` / `port` | `localhost` / 11434 | Only used when `manage: false` |
| `gpus` | true | |
| `models_volume` | - | Bind-mount to persist pulled models |
| `pull_models` | `[]` | Models to `ollama pull` right after startup |

Ollama can serve multiple models from one running instance, so it's started once per experiment.

### llama.cpp

| Option | Default | Notes |
|---|---|---|
| `model_path` | *required* | Host path to a GGUF file. **One model per running instance.** |
| `port` | 8080 | |
| `context_length` | 4096 | |
| `gpu_layers` | 0 | > 0 offloads layers to GPU |
| `threads` | - | |

### OpenAI-compatible

| Option | Default | Notes |
|---|---|---|
| `endpoint` | *required* | e.g. `https://api.openai.com/v1` |
| `api_key` | - | Bearer token |
| `model` | *required* | Fallback model id if the API doesn't expose `/models` |

Nothing is started or stopped for this provider type — it's always-on and unmanaged.

---

## Adding New Providers

1. Implement `infrastructure/providers/<name>_provider.py`, subclassing `infrastructure.providers.base.Provider` and
   implementing `start`, `stop`, `_health_check`, `list_models`, and `endpoint`.
2. Register it in `infrastructure/providers/registry.py`:
   ```python
   _REGISTRY["my_provider"] = MyProvider
   ```
3. Add its configuration schema to `PROVIDER_CONFIG_SCHEMAS` in
   `apps/api/app/api/routes/providers.py` so the web wizard renders the right fields.
4. Add a template at `infrastructure/configs/providers/my_provider.yaml`.
5. If it can only serve one model per running instance (like vLLM/llama.cpp), add its type to
   `SINGLE_MODEL_PROVIDER_TYPES` and map its "which model" option key in `_MODEL_OPTION_KEY`,
   both in `apps/api/app/services/experiment_service.py`.

No other file needs to change — the scheduler, runner, CLI, and frontend are all written against
the `Provider` interface, not against specific implementations. See
`infrastructure/templates/docker-compose.provider.template.yml` for a walkthrough with a custom Docker image.

---

## Adding New Benchmarks

Benchmarks are never hand-maintained in this codebase — `apps/api/app/services/benchmarks_service.py`
queries lm-evaluation-harness's own `TaskManager` registry directly, so every benchmark the
installed harness version supports (including custom YAML task definitions you drop into its
`tasks/` directory) is automatically available to experiments, the CLI, and the web wizard. To add
a benchmark:

1. Follow [lm-evaluation-harness's own task-authoring guide](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/new_task_guide.md)
   to add a new task YAML.
2. Rebuild the backend image (or mount your custom tasks directory into the container) so the
   harness picks it up.
3. Reference the new task name in any experiment's `benchmarks` list — no framework code changes.

---

## Result Format

One JSON file per model at `results/<sanitized-model-name>.json`, containing a **list** of
result entries that accumulate over time (a rerun of the same benchmark is appended as a new
timestamped entry by default, never silently overwritten):

```json
[
  {
    "metadata": {
      "model": "llama3.2:1b",
      "provider": "ollama",
      "benchmark": "arc_easy",
      "timestamp": "2026-07-31T10:15:00Z",
      "duration_seconds": 143.2,
      "harness_version": "0.4.5",
      "git_commit": "a1b2c3d",
      "execution_config": {
        "provider_type": "ollama",
        "model_args": "model=llama3.2:1b,base_url=...",
        "limit": 50
      }
    },
    "metrics": {
      "acc": 0.71,
      "acc_stderr": 0.02,
      "acc_norm": 0.69,
      "acc_norm_stderr": 0.021
    },
    "raw": { "...": "full, untouched lm-evaluation-harness output" }
  }
]
```

The dashboard's summary matrix shows the *first* metric key from each result as the "primary"
score (lm-evaluation-harness typically orders `acc`/`exact_match`-style metrics first); the
detailed view exposes every metric in `metrics`, plus the complete untouched harness output under
`raw` for full auditability.

---

## REST API

Base path: `/api/v1`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/providers` | List provider types + configuration schemas |
| `GET` | `/providers/{type}/models?...` | Probe a provider for available models (Ollama/OpenAI-compatible only) |
| `GET` | `/benchmarks` | List benchmarks available via lm-evaluation-harness |
| `GET` | `/experiments` | List all experiments (summary view) |
| `POST` | `/experiments` | Create an experiment from a definition |
| `GET` | `/experiments/{id}` | Full experiment record, including all jobs |
| `POST` | `/experiments/{id}/run` | Start execution in the background |
| `POST` | `/experiments/{id}/cancel` | Request cancellation |
| `GET` | `/experiments/{id}/logs/{job_id}?tail=N` | Tail a job's execution log |
| `GET` | `/results` | Dashboard summary matrix (model × benchmark, primary scores) |
| `GET` | `/results/{model}` | Every stored result for a model |
| `GET` | `/results/{model}/{benchmark}` | The latest detailed result (all metrics) for one benchmark |

Interactive OpenAPI docs are available at `http://localhost:8000/docs` once the backend is
running.

---

## Development Setup

Running the backend and frontend outside Docker (faster iteration loop):

```bash
# Backend
cd llm-benchmarking-framework
python -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt
export BENCHLAB_ROOT=$(pwd)
uvicorn apps.api.app.main:app --reload

# Frontend (separate terminal)
cd apps/web
npm install
npm run dev   # proxies /api to http://localhost:8000, see vite.config.js
```

Note: launching real provider containers still requires Docker even in this mode, since
`infrastructure/providers/docker_runtime.py` talks to the Docker Engine API directly.

Run the fault-isolation tests (no Docker required):

```bash
PYTHONPATH=. python -m tests.test_scheduler_fault_isolation
PYTHONPATH=. python -m tests.test_experiment_fault_isolation_e2e
```

---

## Troubleshooting

**A provider container never becomes "ready" and the job times out.**
Check its logs — every provider exposes a `.logs()` helper, and container logs are also visible
with `docker logs benchlab-<provider>-<name>`. Common causes: the model doesn't fit in
`gpu_memory_utilization`, a gated HF model needs `hf_token`, or the wrong `gpu_layers`/`gpus`
setting was used for the available hardware.

**`docker: permission denied` from the backend.**
The backend needs access to `/var/run/docker.sock`. On Linux, ensure the user running
`docker compose` is in the `docker` group, or run Compose with sufficient privileges.

**A job fails with a connection error to the provider.**
Confirm the provider container and the backend are on the same Docker network
(`benchlab-network` by default — see [Docker Architecture](#docker-architecture)). If you changed
`BENCHLAB_DOCKER_NETWORK`, make sure it matches between `docker-compose.yml` and your environment.

**GPU not detected inside a provider container.**
Install the NVIDIA Container Toolkit on the host and confirm `docker run --gpus all ...` works
outside this framework first; the `gpus: true` option in provider configs maps directly to a
Docker device request.

**Results aren't showing up on the dashboard.**
The dashboard only reflects `results/*.json`. If a job status shows `FAILED`, no result file is
written for that job — check its log via `bench experiment logs <experiment-id> <job-id>`.

**An experiment is stuck in `RUNNING` after a backend restart.**
Experiment status is only updated by the thread that's actively running it; if the backend
process was killed mid-run, that experiment will remain `RUNNING` in its JSON record until you
cancel it (`bench experiment cancel <id>`) or manually edit the record. A future improvement is a
startup reconciliation pass that detects and re-flags such orphaned runs.

---

## Frequently Asked Questions

**Does this framework reimplement any benchmark logic?**
No. Every evaluation is delegated to `lm-evaluation-harness` as a subprocess; `core/runner/harness_runner.py`
only builds the CLI invocation and parses its JSON output.

**Can I benchmark a model I'm already serving myself (not via this framework)?**
Yes — set `manage: false` for Ollama and point it at your `host`/`port`, or use the
`openai_compatible` provider for any other already-running OpenAI-compatible endpoint.

**What happens if I list the same benchmark for the same model twice across two runs?**
Both results are kept. `infrastructure/storage/result_store.py` appends new entries by default; pass
`overwrite=True` (exposed as future CLI/API flag if you need it) to replace instead.

**Why doesn't `vllm`/`llamacpp` support listing available models ahead of time?**
Because they serve exactly one model, chosen at launch. There's no catalog to browse — you type
the model id or file path directly when creating the experiment.

**Can I run more than one experiment at the same time?**
Yes. Each experiment runs on its own background thread in the backend; unrelated experiments
don't block each other. Concurrency *within* a single provider instance is still governed by that
provider's `supports_concurrency` flag (see [Execution Modes & Fault Isolation](#execution-modes--fault-isolation)).

**Is there a database?**
No — experiments and results are plain JSON files under `experiments/` and `results/`. This keeps
the "only persist what's necessary, everything else ephemeral" requirement simple and auditable
(you can `cat`/`jq` any of it directly). The storage layer is isolated behind
`infrastructure/storage/experiment_store.py` / `infrastructure/storage/result_store.py` if you want to swap in a real database
later.
