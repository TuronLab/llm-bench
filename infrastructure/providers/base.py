"""
Provider abstraction layer.

Every inference backend (vLLM, Ollama, llama.cpp, OpenAI-compatible APIs, ...)
implements the `Provider` interface defined here. The benchmark engine and the
scheduler only ever talk to this interface, never to a concrete implementation,
which keeps the framework backend-agnostic and trivially extensible.

To add a new provider:
    1. Subclass `Provider`.
    2. Implement `start`, `stop`, `wait_until_ready`, `list_models`, `endpoint`.
    3. Register it in `infrastructure/providers/registry.py`.
No other part of the codebase needs to change.
"""

from __future__ import annotations

import abc
import dataclasses
import enum
import time
from typing import Any, Optional


class ProviderStatus(str, enum.Enum):
    """Lifecycle state of a provider instance."""

    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    ERROR = "error"
    STOPPING = "stopping"


class ProviderError(RuntimeError):
    """Raised when a provider fails to start, stop, or respond."""


@dataclasses.dataclass
class ModelInfo:
    """Minimal, provider-agnostic description of a model."""

    id: str
    name: str
    size_bytes: Optional[int] = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ProviderConfig:
    """
    Generic configuration bag for a provider instance.

    Concrete providers read whichever keys they need out of `options`. The
    schema for each provider's `options` is documented in
    `infrastructure/configs/providers/<provider>.yaml` and enforced by each provider's
    `validate_config` implementation.
    """

    name: str
    type: str
    options: dict[str, Any] = dataclasses.field(default_factory=dict)
    # If True, the provider container is left running after use instead of
    # being torn down automatically. Useful for local, already-running
    # servers (e.g. an Ollama instance the user manages themselves).
    keep_alive: bool = False
    # Whether this provider instance can safely serve more than one
    # concurrent benchmark job. Most local single-GPU deployments cannot.
    supports_concurrency: bool = False


class Provider(abc.ABC):
    """
    Common interface every inference provider must implement.

    Lifecycle contract:
        start()              -> begin launching the backend (may be async under the hood)
        wait_until_ready()   -> block (with timeout) until the endpoint accepts requests
        endpoint()           -> return the OpenAI-compatible base URL to hit
        list_models()        -> enumerate models currently servable
        stop()                -> tear down the backend and release resources
    """

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.status: ProviderStatus = ProviderStatus.STOPPED
        self._last_error: Optional[str] = None

    # -- lifecycle -----------------------------------------------------

    @abc.abstractmethod
    def start(self) -> None:
        """Launch the provider (container, subprocess, or no-op for remote APIs)."""
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self) -> None:
        """Tear down the provider and release any resources it holds."""
        raise NotImplementedError

    def wait_until_ready(self, timeout: float = 300.0, poll_interval: float = 2.0) -> None:
        """
        Poll the provider until it reports readiness or `timeout` seconds elapse.

        Default implementation repeatedly calls `_health_check`; providers may
        override this entirely if a different readiness strategy is needed.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._health_check():
                self.status = ProviderStatus.READY
                return
            time.sleep(poll_interval)
        self.status = ProviderStatus.ERROR
        raise ProviderError(
            f"Provider '{self.config.name}' did not become ready within {timeout}s"
        )

    @abc.abstractmethod
    def _health_check(self) -> bool:
        """Return True if the provider's endpoint is currently reachable and healthy."""
        raise NotImplementedError

    # -- introspection ---------------------------------------------------

    @abc.abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """Return the models currently available through this provider."""
        raise NotImplementedError

    @abc.abstractmethod
    def endpoint(self) -> str:
        """Return the base URL lm-evaluation-harness should target."""
        raise NotImplementedError

    def api_key(self) -> Optional[str]:
        """Return the API key to use, if any. Defaults to none (local providers)."""
        return self.config.options.get("api_key")

    def harness_model_type(self) -> str:
        """
        Return the lm-evaluation-harness `--model` value appropriate for this
        provider. Nearly all providers here expose an OpenAI-compatible
        chat/completions API, so `local-completions` / `local-chat-completions`
        (the harness's generic OpenAI-API model type) is the sane default.
        """
        return self.config.options.get("harness_model_type", "local-chat-completions")

    def harness_model_args(self, model: str) -> str:
        """
        Build the comma-separated `--model_args` string lm-evaluation-harness
        expects for OpenAI-compatible backends. Providers may override this
        for backends with different requirements.
        """
        base = self.endpoint().rstrip("/")
        args = {
            "model": model,
            "base_url": f"{base}/chat/completions",
            "num_concurrent": 1 if not self.config.supports_concurrency else self.config.options.get("num_concurrent", 4),
            "max_retries": 3,
            "tokenized_requests": False,
        }
        if self.api_key():
            args["api_key"] = self.api_key()
        return ",".join(f"{k}={v}" for k, v in args.items())

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def __repr__(self) -> str:  # pragma: no cover - convenience only
        return f"<{self.__class__.__name__} name={self.config.name!r} status={self.status.value}>"
