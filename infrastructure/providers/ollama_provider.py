"""
Ollama provider: talks to an Ollama server, launching a container for it
unless the user points to an already-running instance (`manage: false`).
"""

from __future__ import annotations

import logging

import httpx

from infrastructure.providers.base import ModelInfo, Provider, ProviderError, ProviderStatus
from infrastructure.providers.docker_runtime import DockerContainerRuntime

logger = logging.getLogger("benchlab.providers.ollama")

DEFAULT_IMAGE = "ollama/ollama:latest"
DEFAULT_PORT = 11434


class OllamaProvider(Provider):
    """
    Expected `config.options` keys:
        host (str): hostname of an existing Ollama server. Default "localhost".
        port (int): default 11434.
        manage (bool): if True (default), launch/stop a container. If False,
            connect to an externally managed instance instead.
        image (str): default "ollama/ollama:latest".
        gpus (bool): default False; set True only for NVIDIA-enabled Docker hosts.
        models_volume (str): host path mounted at /root/.ollama for model cache.
        pull_models (list[str]): models to `ollama pull` right after startup.
    """

    def __init__(self, config):
        super().__init__(config)
        opts = config.options
        self._host = opts.get("host", "localhost")
        self._port = int(opts.get("port", DEFAULT_PORT))
        self._manage = bool(opts.get("manage", True))
        self._container_name = f"benchlab-ollama-{config.name}"
        self._runtime = DockerContainerRuntime() if self._manage else None

    def start(self) -> None:
        self.status = ProviderStatus.STARTING
        if not self._manage:
            # Externally managed instance; nothing to launch.
            return
        opts = self.config.options
        volumes = {}
        if opts.get("models_volume"):
            volumes[opts["models_volume"]] = {"bind": "/root/.ollama", "mode": "rw"}
        try:
            self._runtime.run(
                name=self._container_name,
                image=opts.get("image", DEFAULT_IMAGE),
                ports={f"{DEFAULT_PORT}/tcp": self._port},
                volumes=volumes,
                gpus=opts.get("gpus", False),
            )
        except Exception as exc:  # noqa: BLE001
            self.status = ProviderStatus.ERROR
            self._last_error = str(exc)
            raise ProviderError(f"Failed to start Ollama container: {exc}") from exc

    def stop(self) -> None:
        if not self._manage:
            self.status = ProviderStatus.STOPPED
            return
        self.status = ProviderStatus.STOPPING
        self._runtime.stop(self._container_name)
        self.status = ProviderStatus.STOPPED

    def _health_check(self) -> bool:
        try:
            resp = httpx.get(f"{self._base()}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def pull_configured_models(self) -> None:
        for model in self.config.options.get("pull_models", []):
            logger.info("Pulling Ollama model %s", model)
            httpx.post(f"{self._base()}/api/pull", json={"name": model}, timeout=None)

    def list_models(self) -> list[ModelInfo]:
        try:
            resp = httpx.get(f"{self._base()}/api/tags", timeout=10.0)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return [
                ModelInfo(id=m["name"], name=m["name"], size_bytes=m.get("size"))
                for m in models
            ]
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not list Ollama models: {exc}") from exc

    def _base(self) -> str:
        if self._manage:
            # Managed container: reachable via the shared Docker network by
            # container name, not 'localhost' (see docker_runtime.py).
            return f"http://{self._container_name}:{DEFAULT_PORT}"
        return f"http://{self._host}:{self._port}"

    def endpoint(self) -> str:
        # Ollama exposes an OpenAI-compatible surface under /v1
        return f"{self._base()}/v1"

    def logs(self, tail: int = 200) -> str:
        if not self._runtime:
            return ""
        return self._runtime.logs(self._container_name, tail=tail)
