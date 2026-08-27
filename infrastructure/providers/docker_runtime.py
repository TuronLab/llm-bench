"""
Thin wrapper around the Docker Engine API (via the `docker` SDK) used by
container-based providers (vLLM, Ollama, llama.cpp) to start and stop their
own ephemeral inference server containers.

Networking note
----------------
The API application (`apps/api`) runs inside a container and talks to the host's Docker
daemon over the mounted socket ("Docker outside of Docker") to launch
provider containers. Because of that, `localhost` from the API container's
network namespace does NOT reach a sibling provider container's published
port. Instead, every provider container launched here is attached to the
same user-defined bridge network as the API service (`BENCHLAB_DOCKER_NETWORK`,
matching the `benchlab` network in docker-compose.yml), which gives it a
resolvable DNS name equal to its container name. Providers must therefore
build their `endpoint()` using the container name + the container's
*internal* port, not `localhost` + the host-published port. The host port
mapping is kept anyway so a human can also reach the provider directly for
debugging (e.g. `curl localhost:8000/v1/models`).

Kept separate from `base.Provider` so that non-container providers (e.g. a
remote OpenAI-compatible API) don't depend on Docker at all.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("benchlab.providers.docker")

try:
    import docker
    from docker.errors import APIError, ImageNotFound, NotFound
except ImportError:  # pragma: no cover - docker SDK is an optional runtime dep
    docker = None
    APIError = ImageNotFound = NotFound = Exception

DEFAULT_NETWORK = os.environ.get("BENCHLAB_DOCKER_NETWORK", "benchlab-network")


class DockerRuntimeError(RuntimeError):
    pass


class DockerContainerRuntime:
    """
    Manages the lifecycle of a single Docker container that hosts an
    inference server. Containers are labeled so they can be identified and
    cleaned up even after an unexpected API service restart.
    """

    LABEL_KEY = "benchlab.managed"

    def __init__(self) -> None:
        if docker is None:
            raise DockerRuntimeError(
                "The 'docker' Python package is required to manage provider "
                "containers. Install it with `pip install docker`."
            )
        self._client = docker.from_env()

    def run(
        self,
        *,
        name: str,
        image: str,
        command: Optional[list[str]] = None,
        environment: Optional[dict[str, str]] = None,
        ports: Optional[dict[str, int]] = None,
        volumes: Optional[dict[str, dict[str, str]]] = None,
        gpus: bool = False,
        shm_size: Optional[str | int] = None,
        network: Optional[str] = None,
        extra_labels: Optional[dict[str, str]] = None,
    ) -> str:
        """Start (or reuse) a container and return its id."""
        self.remove_if_exists(name)
        device_requests = None
        if gpus:
            device_requests = [
                docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
            ]
        labels = {self.LABEL_KEY: "true", "benchlab.provider": name}
        labels.update(extra_labels or {})
        try:
            try:
                self._client.images.get(image)
                logger.info("Docker image %s already available", image)
            except ImageNotFound:
                logger.info("Docker image %s not found; downloading it now", image)
                self._client.images.pull(image)
                logger.info("Finished downloading Docker image %s", image)
            container = self._client.containers.run(
                image,
                command=command,
                name=name,
                environment=environment or {},
                ports=ports or {},
                volumes=volumes or {},
                device_requests=device_requests,
                shm_size=shm_size,
                network=network or DEFAULT_NETWORK,
                detach=True,
                labels=labels,
            )
        except APIError as exc:
            raise DockerRuntimeError(
                f"Failed to prepare image or start container '{name}': {exc}"
            ) from exc
        logger.info("Started container %s (%s) from image %s on network %s",
                    name, container.id[:12], image, network or DEFAULT_NETWORK)
        return container.id

    def stop(self, name: str, timeout: int = 10) -> None:
        try:
            container = self._client.containers.get(name)
        except NotFound:
            return
        try:
            container.stop(timeout=timeout)
            container.remove(force=True)
            logger.info("Stopped and removed container %s", name)
        except APIError as exc:
            logger.warning("Error stopping container %s: %s", name, exc)

    def remove_if_exists(self, name: str) -> None:
        try:
            container = self._client.containers.get(name)
            container.remove(force=True)
            logger.info("Removed pre-existing container %s", name)
        except NotFound:
            return

    def logs(self, name: str, tail: int = 200) -> str:
        try:
            container = self._client.containers.get(name)
        except NotFound:
            return ""
        return container.logs(tail=tail).decode("utf-8", errors="replace")

    def is_running(self, name: str) -> bool:
        try:
            container = self._client.containers.get(name)
            container.reload()
            return container.status == "running"
        except NotFound:
            return False

    def list_managed(self) -> list[dict[str, Any]]:
        containers = self._client.containers.list(
            all=True, filters={"label": f"{self.LABEL_KEY}=true"}
        )
        return [{"name": c.name, "status": c.status, "id": c.id[:12]} for c in containers]
