"""
llama.cpp provider: launches `llama-server` (llama.cpp's OpenAI-compatible
HTTP server) inside a container, serving a local GGUF model file.
"""

from __future__ import annotations

import logging
import os

import httpx

from infrastructure.providers.base import ModelInfo, Provider, ProviderError, ProviderStatus
from infrastructure.providers.docker_runtime import DockerContainerRuntime

logger = logging.getLogger("benchlab.providers.llamacpp")

DEFAULT_IMAGE = "ghcr.io/ggml-org/llama.cpp:server"
DEFAULT_PORT = 8080


class LlamaCppProvider(Provider):
    """
    Expected `config.options` keys:
        model_path (str, required): host path to a GGUF model file.
        image (str): default "ghcr.io/ggerganov/llama.cpp:server".
        port (int): default 8080.
        context_length (int): `--ctx-size`, default 4096.
        gpu_layers (int): `--n-gpu-layers`, default 0 (CPU only).
        threads (int): `--threads`, optional.
        extra_args (list[str]): additional CLI flags.
    """

    def __init__(self, config):
        super().__init__(config)
        opts = config.options
        if "model_path" not in opts:
            raise ProviderError("llama.cpp provider requires 'model_path' in options")
        self._model_path = opts["model_path"]
        self._port = int(opts.get("port", DEFAULT_PORT))
        self._image = opts.get("image", DEFAULT_IMAGE)
        self._container_name = f"benchlab-llamacpp-{config.name}"
        self._runtime = DockerContainerRuntime()

    def start(self) -> None:
        self.status = ProviderStatus.STARTING
        opts = self.config.options
        model_dir = os.path.dirname(self._model_path)
        model_file = os.path.basename(self._model_path)
        cmd = [
            "--model", f"/models/{model_file}",
            "--ctx-size", str(opts.get("context_length", 4096)),
            "--n-gpu-layers", str(opts.get("gpu_layers", 0)),
            "--port", str(self._port),
            "--host", "0.0.0.0",
        ]
        if opts.get("threads"):
            cmd.extend(["--threads", str(opts["threads"])])
        cmd.extend(opts.get("extra_args", []))

        try:
            self._runtime.run(
                name=self._container_name,
                image=self._image,
                command=cmd,
                ports={f"{self._port}/tcp": self._port},
                volumes={model_dir: {"bind": "/models", "mode": "ro"}},
                gpus=opts.get("gpu_layers", 0) > 0,
            )
        except Exception as exc:  # noqa: BLE001
            self.status = ProviderStatus.ERROR
            self._last_error = str(exc)
            raise ProviderError(f"Failed to start llama.cpp container: {exc}") from exc

    def stop(self) -> None:
        self.status = ProviderStatus.STOPPING
        self._runtime.stop(self._container_name)
        self.status = ProviderStatus.STOPPED

    def _health_check(self) -> bool:
        try:
            resp = httpx.get(f"{self.endpoint()}/models", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[ModelInfo]:
        # llama-server serves exactly one model per instance.
        name = os.path.basename(self._model_path)
        return [ModelInfo(id=name, name=name)]

    def endpoint(self) -> str:
        # Reachable from the API container via the shared Docker network
        # (see infrastructure/providers/docker_runtime.py for why this isn't 'localhost').
        return f"http://{self._container_name}:{self._port}/v1"

    def logs(self, tail: int = 200) -> str:
        return self._runtime.logs(self._container_name, tail=tail)
