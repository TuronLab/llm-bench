---
title: LLM Benchmarking Framework
---

# LLM Benchmarking Framework

Self-hosted framework for evaluating LLM deployments across inference backends. It orchestrates local or remote providers, runs `lm-evaluation-harness`, and preserves the configuration, logs, raw output, and metrics for each experiment.

It is designed for comparisons that public leaderboards do not always cover: specific model revisions, quantized variants, and models deployed on your own hardware.

## Documentation

- [Architecture and execution model]({{ '/architecture/' | relative_url }})
- [Providers and experiment definitions]({{ '/providers/' | relative_url }})
- [Supported benchmarks]({{ '/benchmarks/' | relative_url }})

## Quick start

To use `llm-bench`, start `backend`, which runs evaluations, and `frontend`, the browser dashboard for creating comparisons, tracking progress, and reviewing scores.

```bash
docker compose up -d --build backend frontend
docker compose run --build --rm cli experiment run experiments/examples/quickstart.yaml
```

This starts the API and dashboard, downloads the two small Ollama models in the example, and runs a short comparison.

## Native CLI

With the API running, install and use the CLI from the repository root:

```bash
uv tool install .
export BENCHLAB_API_URL=http://localhost:8000/api/v1
llm-bench experiment run experiments/examples/quickstart.yaml
```

The native CLI only needs an accessible API service. Managed vLLM, Ollama, and llama.cpp providers still require Docker; the Hugging Face provider runs locally through Transformers. Use `openai_compatible` or Ollama with `manage: false` for an external setup.

For development, install the local API group and run it without Compose:

```bash
uv sync --group api
uv run --group api uvicorn apps.api.app.main:app --reload
```

The command-line interface can list the exact benchmarks supported by the installed `lm-evaluation-harness` version:

```bash
llm-bench benchmarks list
```

## Publishing this site

This directory is a Jekyll source directory for GitHub Pages. In the repository's **Settings → Pages**, choose **Deploy from a branch**, select the default branch, and select the `/docs` folder. GitHub Pages will build and publish the site after pushes to that branch.

For local preview, run Jekyll from this directory with your usual Bundler setup:

```bash
cd docs
bundle exec jekyll serve
```

The repository source, templates, and Docker configuration are available on [GitHub]({{ site.repository_url }}).
