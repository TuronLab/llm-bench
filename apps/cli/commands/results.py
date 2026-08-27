from __future__ import annotations

import typer
from rich.table import Table

from apps.cli.client import client, console

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_results():
    """Show the model x benchmark summary matrix (primary scores)."""
    data = client.get("/results")
    matrix = data["matrix"]
    benchmarks = sorted({b for row in matrix.values() for b in row})
    table = Table(title="Results Summary")
    table.add_column("Model", style="cyan")
    for bench in benchmarks:
        table.add_column(bench)
    for model, row in matrix.items():
        cells = []
        for bench in benchmarks:
            cell = row.get(bench)
            cells.append(f"{cell['value']:.4f}" if cell and cell.get("value") is not None else "-")
        table.add_row(model, *cells)
    console.print(table)


@app.command("show")
def show(model: str = typer.Argument(...)):
    """Show every stored result (all runs, all benchmarks) for a model."""
    data = client.get(f"/results/{model}")
    table = Table(title=f"Results for {model}")
    table.add_column("Benchmark")
    table.add_column("Timestamp")
    table.add_column("Metrics")
    for result in data["results"]:
        meta = result["metadata"]
        metrics = ", ".join(f"{k}={v}" for k, v in result["metrics"].items())
        table.add_row(meta["benchmark"], meta["timestamp"], metrics)
    console.print(table)
