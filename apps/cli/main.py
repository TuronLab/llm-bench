"""
`bench` -- command line interface for the LLM Benchmarking Framework.

The CLI is a thin client over the REST API exposed by the backend service,
so it works identically whether the backend is running locally via Docker
Compose or on a remote host (configure with `BENCHLAB_API_URL`).
"""

from __future__ import annotations

import typer

from apps.cli.commands import benchmarks, dashboard, experiments, models, providers, results

app = typer.Typer(
    name="bench",
    help="Benchmark LLMs across multiple inference providers using lm-evaluation-harness.",
    no_args_is_help=True,
    add_completion=True,
)

app.add_typer(providers.app, name="providers", help="Inspect available inference providers.")
app.add_typer(models.app, name="models", help="List models available through a provider.")
app.add_typer(benchmarks.app, name="benchmarks", help="List benchmarks available via lm-evaluation-harness.")
app.add_typer(experiments.app, name="experiment", help="Create, validate, run, and monitor experiments.")
app.add_typer(results.app, name="results", help="Inspect stored benchmark results.")
app.command(name="dashboard")(dashboard.open_dashboard)

if __name__ == "__main__":
    app()
