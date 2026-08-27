from __future__ import annotations

import time
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from apps.cli.client import client, console, error_console
from infrastructure.storage.schemas import ExperimentDefinition

app = typer.Typer(no_args_is_help=True)


def _load_definition(path: Path) -> ExperimentDefinition:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ExperimentDefinition.model_validate(raw)


@app.command("validate")
def validate(experiment_file: Path = typer.Argument(..., exists=True, help="Path to experiment YAML")):
    """Validate an experiment YAML file without submitting it."""
    try:
        definition = _load_definition(experiment_file)
    except ValidationError as exc:
        error_console.print(f"Invalid experiment file:\n{exc}")
        raise typer.Exit(code=1)
    n_jobs = len(definition.models) * len(definition.benchmarks)
    console.print(
        f"[bold green]Valid.[/bold green] '{definition.name}' will run "
        f"{n_jobs} jobs ({len(definition.models)} models x {len(definition.benchmarks)} benchmarks) "
        f"in {definition.execution.mode.value} mode."
    )


@app.command("create")
def create(
    experiment_file: Path = typer.Argument(
        None, help="Path to experiment YAML. Omit to launch the interactive wizard."
    )
):
    """Submit an experiment definition to the API service (does not start execution)."""
    if experiment_file is None:
        definition = _interactive_wizard()
    else:
        definition = _load_definition(experiment_file)
    record = client.post("/experiments", json=definition.model_dump(mode="json"))
    console.print(f"Created experiment [bold cyan]{record['id']}[/bold cyan] ('{definition.name}')")
    console.print("Run it with: [bold]bench experiment run " + record["id"] + "[/bold]")


def _interactive_wizard() -> ExperimentDefinition:
    """Prompt-driven experiment creation, mirroring the web UI's wizard steps."""
    from infrastructure.storage.schemas import ExecutionConfig, ExecutionMode, ProviderSpec

    console.print("[bold]Experiment creation wizard[/bold]")
    name = typer.prompt("Experiment name")

    providers_data = client.get("/providers")
    provider_type = typer.prompt(
        f"Provider type [{', '.join(providers_data['types'])}]",
        default=providers_data["types"][0],
    )
    options = {}
    for field in providers_data["schemas"].get(provider_type, []):
        default = field.get("default")
        value = typer.prompt(field["label"], default=str(default) if default is not None else "")
        if value:
            options[field["key"]] = value

    models = [m.strip() for m in typer.prompt("Models (comma-separated)").split(",") if m.strip()]
    benchmarks = [b.strip() for b in typer.prompt("Benchmarks (comma-separated)").split(",") if b.strip()]

    mode = typer.prompt("Execution mode [sequential/parallel]", default="sequential")
    workers = 1
    if mode == "parallel":
        workers = int(typer.prompt("Number of workers", default="2"))

    return ExperimentDefinition(
        name=name,
        provider=ProviderSpec(type=provider_type, options=options),
        models=models,
        benchmarks=benchmarks,
        execution=ExecutionConfig(mode=ExecutionMode(mode), workers=workers),
    )


@app.command("run")
def run(
    experiment: str = typer.Argument(..., help="Experiment YAML path OR an existing experiment ID"),
    watch: bool = typer.Option(True, help="Stream progress until completion"),
):
    """Create (if given a file) and run an experiment, optionally streaming progress."""
    experiment_id = experiment
    path = Path(experiment)
    if path.exists():
        definition = _load_definition(path)
        record = client.post("/experiments", json=definition.model_dump(mode="json"))
        experiment_id = record["id"]
        console.print(f"Created experiment [bold cyan]{experiment_id}[/bold cyan]")

    client.post(f"/experiments/{experiment_id}/run")
    console.print(f"Started experiment [bold cyan]{experiment_id}[/bold cyan]")

    if watch:
        _watch_experiment(experiment_id)


def _watch_experiment(experiment_id: str) -> None:
    started_at = time.monotonic()
    last_preparation_notice = -15.0
    previous_statuses: dict[str, str] = {}
    console.print(
        "[dim]Preparing the provider and configured models. This can take several "
        "minutes on the first run while images or models download.[/dim]"
    )
    console.print(
        "[dim]Detailed backend logs: docker compose logs -f --timestamps backend[/dim]"
    )
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} jobs"),
        console=console,
    ) as progress:
        task_id = progress.add_task("Running experiment", total=1)
        while True:
            record = client.get(f"/experiments/{experiment_id}")
            jobs = record["jobs"]
            total = len(jobs) or 1
            done = sum(1 for j in jobs if j["status"] in ("completed", "failed", "cancelled"))
            progress.update(task_id, total=total, completed=done)

            pending = sum(1 for j in jobs if j["status"] == "pending")
            elapsed = int(time.monotonic() - started_at)
            if pending == total and elapsed - last_preparation_notice >= 15:
                console.print(
                    "[dim]Still preparing provider/models "
                    f"({elapsed}s elapsed; {pending}/{total} jobs pending).[/dim]"
                )
                last_preparation_notice = elapsed

            for job in jobs:
                old_status = previous_statuses.get(job["id"])
                new_status = job["status"]
                if old_status is not None and old_status != new_status:
                    console.print(
                        f"[cyan]{job['model']}[/cyan] / {job['benchmark']}: "
                        f"[bold]{new_status}[/bold]"
                    )
                previous_statuses[job["id"]] = new_status
            if record["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(3)
    console.print(f"Experiment finished with status: [bold]{record['status']}[/bold]")
    _print_job_table(record["jobs"])


def _print_job_table(jobs: list[dict]) -> None:
    table = Table(title="Jobs")
    table.add_column("Model")
    table.add_column("Benchmark")
    table.add_column("Status")
    table.add_column("Error")
    for job in jobs:
        style = {
            "completed": "green",
            "failed": "red",
            "running": "yellow",
        }.get(job["status"], "white")
        table.add_row(job["model"], job["benchmark"], f"[{style}]{job['status']}[/{style}]", job.get("error") or "")
    console.print(table)


@app.command("status")
def status(experiment_id: str = typer.Argument(...)):
    """Show current status and job breakdown for an experiment."""
    record = client.get(f"/experiments/{experiment_id}")
    console.print(f"Experiment: [bold]{record['definition']['name']}[/bold] ({record['status']})")
    _print_job_table(record["jobs"])


@app.command("logs")
def logs(
    experiment_id: str = typer.Argument(...),
    job_id: str = typer.Argument(...),
    tail: int = typer.Option(200, help="Number of lines to show"),
):
    """Show execution logs for a specific job within an experiment."""
    data = client.get(f"/experiments/{experiment_id}/logs/{job_id}", params={"tail": tail})
    for line in data["lines"]:
        console.print(line)


@app.command("cancel")
def cancel(experiment_id: str = typer.Argument(...)):
    """Cancel a running experiment."""
    client.post(f"/experiments/{experiment_id}/cancel")
    console.print(f"[bold yellow]Cancellation requested[/bold yellow] for {experiment_id}")


@app.command("list")
def list_experiments():
    """List all known experiments."""
    data = client.get("/experiments")
    table = Table(title="Experiments")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Jobs")
    for exp in data["experiments"]:
        table.add_row(exp["id"], exp["name"], exp["status"], str(exp["total_jobs"]))
    console.print(table)
