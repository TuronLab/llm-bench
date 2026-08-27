"""
Central registry mapping provider `type` strings (as used in experiment YAML
and API payloads) to concrete `Provider` subclasses.

Adding a new provider is a two-step process:
    1. Implement the class in `infrastructure/providers/<name>_provider.py`.
    2. Add one line to `_REGISTRY` below.
No other file in the framework needs to change.
"""

from __future__ import annotations

from infrastructure.providers.base import Provider, ProviderConfig
from infrastructure.providers.llamacpp_provider import LlamaCppProvider
from infrastructure.providers.ollama_provider import OllamaProvider
from infrastructure.providers.openai_compatible_provider import OpenAICompatibleProvider
from infrastructure.providers.vllm_provider import VLLMProvider

_REGISTRY: dict[str, type[Provider]] = {
    "vllm": VLLMProvider,
    "ollama": OllamaProvider,
    "llamacpp": LlamaCppProvider,
    "openai_compatible": OpenAICompatibleProvider,
}


def available_provider_types() -> list[str]:
    return sorted(_REGISTRY.keys())


def register_provider(type_name: str, cls: type[Provider]) -> None:
    """Allow third-party code / plugins to register additional providers at runtime."""
    _REGISTRY[type_name] = cls


def create_provider(config: ProviderConfig) -> Provider:
    try:
        cls = _REGISTRY[config.type]
    except KeyError as exc:
        raise ValueError(
            f"Unknown provider type '{config.type}'. "
            f"Available types: {', '.join(available_provider_types())}"
        ) from exc
    return cls(config)
