from __future__ import annotations

from typing import Optional

import typer
from rich.table import Table

from cli.client import client, console

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_models(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider type, e.g. 'ollama'"),
    host: Optional[str] = typer.Option(None, help="Provider host (if applicable)"),
    port: Optional[int] = typer.Option(None, help="Provider port (if applicable)"),
    endpoint: Optional[str] = typer.Option(None, help="Provider endpoint URL (openai_compatible)"),
):
    """List models currently available through a provider."""
    params = {k: v for k, v in {"host": host, "port": port, "endpoint": endpoint}.items() if v is not None}
    data = client.get(f"/providers/{provider}/models", params=params)
    table = Table(title=f"Models available via {provider}")
    table.add_column("Model ID", style="cyan")
    for model in data.get("models", []):
        table.add_row(model.get("id", "?"))
    console.print(table)
