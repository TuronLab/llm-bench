from __future__ import annotations

import typer
from rich.columns import Columns

from cli.client import client, console

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_benchmarks():
    """List benchmarks (tasks) available through lm-evaluation-harness."""
    data = client.get("/benchmarks")
    console.print(Columns(sorted(data["benchmarks"]), equal=True, expand=True))
