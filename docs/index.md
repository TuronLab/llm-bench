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

```bash
docker compose build
docker compose up -d backend frontend
docker compose run --rm cli experiment run experiments/examples/quickstart.yaml
```

The command-line interface can list the exact benchmarks supported by the installed `lm-evaluation-harness` version:

```bash
docker compose run --rm cli benchmarks list
```

## Publishing this site

This directory is a Jekyll source directory for GitHub Pages. In the repository's **Settings → Pages**, choose **Deploy from a branch**, select the default branch, and select the `/docs` folder. GitHub Pages will build and publish the site after pushes to that branch.

For local preview, run Jekyll from this directory with your usual Bundler setup:

```bash
cd docs
bundle exec jekyll serve
```

The repository source, templates, and Docker configuration are available on [GitHub]({{ site.repository_url }}).
