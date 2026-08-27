"""
Enumerates benchmarks (tasks) available through lm-evaluation-harness.

If `lm_eval` is installed in the current environment (e.g. inside the
API container, which bundles it for this purpose), its task registry is
queried directly so the framework always reflects whatever version of the
harness is deployed -- no benchmark list is hand-maintained here. If the
harness isn't importable (e.g. during lightweight local development of the
API alone), a small curated fallback list is returned so the UI/CLI remain
usable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("benchlab.services.benchmarks")

_FALLBACK_BENCHMARKS = [
    "mmlu", "gsm8k", "truthfulqa_mc2", "arc_challenge", "arc_easy",
    "hellaswag", "winogrande", "piqa", "boolq", "openbookqa",
    "humaneval", "bbh", "gpqa", "ifeval",
]


def list_benchmarks() -> list[str]:
    try:
        from lm_eval.tasks import TaskManager  # type: ignore

        manager = TaskManager()
        tasks = sorted(manager.all_tasks)
        if tasks:
            return tasks
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lm-evaluation-harness task registry unavailable (%s); "
            "returning curated fallback benchmark list", exc
        )
    return _FALLBACK_BENCHMARKS
