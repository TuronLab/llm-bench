"""Backend selection and SQLite adapters.

Set ``BENCHLAB_PERSISTENCE=sqlite`` to use one local database. The default is
``json`` for backwards compatibility with existing installations.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from infrastructure.storage.paths import SQLITE_PATH
from infrastructure.storage.sqlite_store import SQLiteStore

_VALID_BACKENDS = {"json", "sqlite"}
_sqlite_store: SQLiteStore | None = None
_sqlite_lock = threading.Lock()


def persistence_backend() -> str:
    backend = os.environ.get("BENCHLAB_PERSISTENCE", "json").lower().strip()
    if backend not in _VALID_BACKENDS:
        raise ValueError(
            f"Unsupported BENCHLAB_PERSISTENCE={backend!r}. Expected one of: {', '.join(sorted(_VALID_BACKENDS))}."
        )
    return backend


def sqlite_store(path: Path | None = None) -> SQLiteStore:
    """Return the process-wide SQLite store (or a dedicated one for tests)."""
    if path is not None:
        return SQLiteStore(path)
    global _sqlite_store
    with _sqlite_lock:
        if _sqlite_store is None:
            _sqlite_store = SQLiteStore(SQLITE_PATH)
        return _sqlite_store


class SQLiteLoadTestingRepository:
    """Adapts SQLiteStore's names to the load-testing repository contract."""

    def __init__(self, store: SQLiteStore):
        self._store = store

    def append(self, result):
        return self._store.append_load_test(result)

    def latest(self):
        return self._store.latest_load_tests()

    def delete(self, model: str, provider: str, concurrent_users: int, timestamp: str) -> bool:
        return self._store.delete_load_test(model, provider, concurrent_users, timestamp)
