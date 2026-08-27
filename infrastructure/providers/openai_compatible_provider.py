"""
OpenAI-compatible provider: talks to any remote (or already-running local)
service that exposes the OpenAI `/v1/chat/completions` API contract, such as
the real OpenAI API, Azure OpenAI, Together AI, Groq, or a hand-rolled proxy.

There is nothing to start or stop here: the framework never manages the
lifecycle of a remote API, it simply points lm-evaluation-harness at it.
"""

from __future__ import annotations

import httpx

from infrastructure.providers.base import ModelInfo, Provider, ProviderError, ProviderStatus


class OpenAICompatibleProvider(Provider):
    """
    Expected `config.options` keys:
        endpoint (str, required): base URL, e.g. "https://api.openai.com/v1".
        api_key (str): bearer token, optional depending on the service.
        model (str): default model id to report via `list_models` if the
            remote API doesn't expose a `/models` listing endpoint.
    """

    def __init__(self, config):
        super().__init__(config)
        opts = config.options
        if "endpoint" not in opts:
            raise ProviderError("OpenAI-compatible provider requires 'endpoint' in options")
        self._endpoint = opts["endpoint"].rstrip("/")

    def start(self) -> None:
        # Remote services are always-on; just verify reachability.
        self.status = ProviderStatus.STARTING

    def stop(self) -> None:
        # Nothing to tear down for a remote, unmanaged API.
        self.status = ProviderStatus.STOPPED

    def _health_check(self) -> bool:
        headers = {"Authorization": f"Bearer {self.api_key()}"} if self.api_key() else {}
        try:
            resp = httpx.get(f"{self._endpoint}/models", headers=headers, timeout=10.0)
            return resp.status_code < 500
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[ModelInfo]:
        headers = {"Authorization": f"Bearer {self.api_key()}"} if self.api_key() else {}
        try:
            resp = httpx.get(f"{self._endpoint}/models", headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [ModelInfo(id=m["id"], name=m["id"]) for m in data]
        except httpx.HTTPError:
            # Some providers don't implement /models; fall back to configured default.
            default = self.config.options.get("model")
            return [ModelInfo(id=default, name=default)] if default else []

    def endpoint(self) -> str:
        return self._endpoint
