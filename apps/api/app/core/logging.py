"""Structured logging setup shared by the API application and, indirectly, the runner."""

from __future__ import annotations

import logging
import sys

from apps.api.app.core.config import settings


def configure_logging() -> None:
    root = logging.getLogger("benchlab")
    if root.handlers:
        return  # already configured (e.g. under a reloader)
    root.setLevel(settings.LOG_LEVEL)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    root.addHandler(handler)
