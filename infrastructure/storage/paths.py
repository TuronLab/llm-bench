"""
Single source of truth for where persistent data lives on disk.

Only experiment definitions, results, and (optionally) logs are ever written
outside of ephemeral container filesystems. All paths are overridable via
environment variables so the same code works identically whether it's
running in the API container, the CLI container, or bare-metal during
development.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("BENCHLAB_ROOT", Path(__file__).resolve().parents[2]))

EXPERIMENTS_DIR = Path(os.environ.get("BENCHLAB_EXPERIMENTS_DIR", PROJECT_ROOT / "experiments"))
RESULTS_DIR = Path(os.environ.get("BENCHLAB_RESULTS_DIR", PROJECT_ROOT / "results"))
BENCHMARK_RESULTS_DIR = Path(os.environ.get("BENCHLAB_BENCHMARK_RESULTS_DIR", RESULTS_DIR / "benchmarks"))
LOAD_TESTING_RESULTS_DIR = Path(os.environ.get("BENCHLAB_LOAD_TESTING_RESULTS_DIR", RESULTS_DIR / "load_testing"))
SQLITE_PATH = Path(os.environ.get("BENCHLAB_SQLITE_PATH", RESULTS_DIR / "benchlab.db"))
LOGS_DIR = Path(os.environ.get("BENCHLAB_LOGS_DIR", PROJECT_ROOT / "logs"))
CONFIGS_DIR = Path(os.environ.get("BENCHLAB_CONFIGS_DIR", PROJECT_ROOT / "infrastructure" / "configs"))

def ensure_directories() -> None:
    for path in (EXPERIMENTS_DIR, RESULTS_DIR, BENCHMARK_RESULTS_DIR, LOAD_TESTING_RESULTS_DIR, LOGS_DIR, CONFIGS_DIR):
        path.mkdir(parents=True, exist_ok=True)
