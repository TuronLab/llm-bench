from __future__ import annotations

import typer
from rich.table import Table

from cli.client import client, console

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_providers():
    """List available provider types and their configuration schema."""
    data = client.get("/providers")
    table = Table(title="Available Providers")
    table.add_column("Type", style="cyan")
    table.add_column("Configurable Options", style="white")
    for provider_type in data["types"]:
        fields = data["schemas"].get(provider_type, [])
        field_names = ", ".join(f["key"] for f in fields)
        table.add_row(provider_type, field_names)
    console.print(table)
