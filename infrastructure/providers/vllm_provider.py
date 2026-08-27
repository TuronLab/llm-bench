"""
vLLM provider: launches an OpenAI-compatible vLLM server inside a container.
"""

from __future__ import annotations

import logging

import httpx

from infrastructure.providers.base import ModelInfo, Provider, ProviderError, ProviderStatus
from infrastructure.providers.docker_runtime import DockerContainerRuntime

logger = logging.getLogger("benchlab.providers.vllm")

DEFAULT_IMAGE = "vllm/vllm-openai:latest"
DEFAULT_PORT = 8000


class VLLMProvider(Provider):
    """
    Expected `config.options` keys:
        model (str, required): HF model id or local path to serve.
        image (str): vLLM docker image, default "vllm/vllm-openai:latest".
        port (int): host port to bind, default 8000.
        tensor_parallel_size (int): default 1.
        gpu_memory_utilization (float): default 0.9.
        dtype (str): default "auto".
        gpus (bool): whether to request GPU devices, default True.
        extra_args (list[str]): additional CLI flags passed to vllm serve.
        hf_token (str): optional Hugging Face token for gated models.
        host_models_dir (str): host path mounted to the container's HF cache.
    """

    def __init__(self, config):
        super().__init__(config)
        self._runtime = DockerContainerRuntime()
        self._container_name = f"benchlab-vllm-{config.name}"
        opts = config.options
        if "model" not in opts:
            raise ProviderError("vLLM provider requires 'model' in options")
        self._model = opts["model"]
        self._port = int(opts.get("port", DEFAULT_PORT))
        self._image = opts.get("image", DEFAULT_IMAGE)
        self._shm_size = opts.get("shm_size", "1g")

    def start(self) -> None:
        self.status = ProviderStatus.STARTING
        opts = self.config.options
        cmd = [
            "--model", self._model,
            "--tensor-parallel-size", str(opts.get("tensor_parallel_size", 1)),
            "--gpu-memory-utilization", str(opts.get("gpu_memory_utilization", 0.9)),
            "--dtype", str(opts.get("dtype", "auto")),
            "--port", str(self._port),
            "--host", "0.0.0.0",
        ]
        cmd.extend(opts.get("extra_args", []))

        env = {}
        # vLLM cannot reliably infer the backend in CPU-only containers (in
        # particular on Docker Desktop/Apple Silicon). Make it explicit while
        # still allowing advanced users to override the target device.
        target_device = opts.get("target_device")
        if target_device or not opts.get("gpus", True):
            env["VLLM_TARGET_DEVICE"] = str(target_device or "cpu")
        if opts.get("hf_token"):
            env["HUGGING_FACE_HUB_TOKEN"] = opts["hf_token"]

        volumes = {}
        if opts.get("host_models_dir"):
            volumes[opts["host_models_dir"]] = {"bind": "/root/.cache/huggingface", "mode": "rw"}

        try:
            self._runtime.run(
                name=self._container_name,
                image=self._image,
                command=cmd,
                environment=env,
                ports={f"{self._port}/tcp": self._port},
                volumes=volumes,
                gpus=opts.get("gpus", True),
                shm_size=self._shm_size,
            )
        except Exception as exc:  # noqa: BLE001
            self.status = ProviderStatus.ERROR
            self._last_error = str(exc)
            raise ProviderError(f"Failed to start vLLM container: {exc}") from exc

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
        try:
            resp = httpx.get(f"{self.endpoint()}/models", timeout=10.0)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [ModelInfo(id=m["id"], name=m["id"]) for m in data]
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not list vLLM models: {exc}") from exc

    def endpoint(self) -> str:
        # Reachable from the API container via the shared Docker network
        # (see infrastructure/providers/docker_runtime.py for why this isn't 'localhost').
        return f"http://{self._container_name}:{self._port}/v1"

    def logs(self, tail: int = 200) -> str:
        return self._runtime.logs(self._container_name, tail=tail)
