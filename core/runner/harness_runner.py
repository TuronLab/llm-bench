"""
Thin orchestration layer around `lm-evaluation-harness`.

This module deliberately contains NO benchmarking logic of its own -- it
only builds the correct `lm_eval` CLI invocation for a given provider/model/
benchmark combination, executes it as a subprocess (inside the runner
container), captures its JSON output, and normalizes it into a
`BenchmarkResult`. All actual evaluation logic lives inside
lm-evaluation-harness itself, exactly as required.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from infrastructure.providers.base import Provider
from infrastructure.storage.paths import LOGS_DIR
from infrastructure.storage.schemas import BenchmarkResult, ResultMetadata

logger = logging.getLogger("benchlab.runner")


class HarnessExecutionError(RuntimeError):
    pass


def _harness_version() -> Optional[str]:
    try:
        out = subprocess.run(
            ["lm_eval", "--version"], capture_output=True, text=True, timeout=15
        )
        return out.stdout.strip() or out.stderr.strip()
    except Exception:  # noqa: BLE001
        return None


def _git_commit() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def build_command(
    provider: Provider,
    model: str,
    benchmark: str,
    output_path: Path,
    extra_args: Optional[dict] = None,
) -> list[str]:
    """
    Construct the `lm_eval` CLI command. `--model` and `--model_args` are
    derived from the provider (provider-agnostic), everything else maps
    directly onto standard lm-evaluation-harness flags.
    """
    cmd = [
        "lm_eval",
        "--model", provider.harness_model_type(),
        "--model_args", provider.harness_model_args(model),
        "--tasks", benchmark,
        "--output_path", str(output_path),
        "--log_samples",
    ]
    extra_args = extra_args or {}
    for key, value in extra_args.items():
        flag = f"--{key}"
        if isinstance(value, bool):
            if value:
                cmd.append(flag)
        else:
            cmd.extend([flag, str(value)])
    return cmd


def run_benchmark(
    provider: Provider,
    model: str,
    benchmark: str,
    experiment_id: str,
    job_id: str,
    extra_args: Optional[dict] = None,
    on_log_line: Optional[Callable[[str], None]] = None,
) -> BenchmarkResult:
    """
    Execute a single (model, benchmark) evaluation against `provider`,
    which must already be started and ready.

    Streams subprocess output line-by-line to `on_log_line` (used for live
    monitoring) and to a persistent log file under `logs/`.
    """
    output_dir = Path("/tmp/benchlab-harness") / experiment_id / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_command(provider, model, benchmark, output_dir, extra_args)
    logger.info("Running lm-evaluation-harness: %s", " ".join(cmd))

    log_path = LOGS_DIR / experiment_id / f"{job_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        assert process.stdout is not None
        for line in process.stdout:
            log_file.write(line)
            log_file.flush()
            if on_log_line:
                on_log_line(line.rstrip("\n"))
        returncode = process.wait()
    duration = time.monotonic() - start

    if returncode != 0:
        raise HarnessExecutionError(
            f"lm-evaluation-harness exited with code {returncode} for "
            f"model={model} benchmark={benchmark}. See {log_path} for details."
        )

    raw_output = _load_harness_output(output_dir)
    metrics = _extract_metrics(raw_output, benchmark)

    metadata = ResultMetadata(
        model=model,
        provider=provider.config.name,
        benchmark=benchmark,
        timestamp=datetime.utcnow(),
        duration_seconds=duration,
        harness_version=_harness_version(),
        git_commit=_git_commit(),
        execution_config={
            "provider_type": provider.config.type,
            "model_args": provider.harness_model_args(model),
            **(extra_args or {}),
        },
    )
    return BenchmarkResult(metadata=metadata, metrics=metrics, raw=raw_output)


def _load_harness_output(output_dir: Path) -> Optional[dict]:
    """lm-evaluation-harness writes `results.json` (or a timestamped variant) under output_path."""
    candidates = sorted(output_dir.rglob("results*.json"))
    if not candidates:
        logger.warning("No results.json found under %s", output_dir)
        return None
    with open(candidates[-1], "r", encoding="utf-8") as fh:
        return json.load(fh)


def _extract_metrics(raw_output: Optional[dict], benchmark: str) -> dict:
    if not raw_output:
        return {}
    results = raw_output.get("results", {})
    task_metrics = results.get(benchmark, {})
    # Filter out the harness's internal bookkeeping keys (e.g. "alias").
    return {k: v for k, v in task_metrics.items() if not k.startswith("_") and k != "alias"}
