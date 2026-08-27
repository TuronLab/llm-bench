"""Endpoints exposing provider type metadata and live model listings."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from infrastructure.providers.base import ProviderConfig, ProviderError
from infrastructure.providers.registry import available_provider_types, create_provider

logger = logging.getLogger("benchlab.api.providers")
router = APIRouter(prefix="/providers", tags=["providers"])

# Describes the user-facing configuration schema for each provider type, so
# the web UI's experiment wizard can dynamically render only relevant fields
# ("Depending on the selected provider, dynamically request the appropriate
# configuration").
PROVIDER_CONFIG_SCHEMAS: dict[str, list[dict]] = {
    "vllm": [
        {"key": "model", "label": "Model", "type": "string", "required": True},
        {"key": "tensor_parallel_size", "label": "Tensor Parallelism", "type": "integer", "default": 1},
        {"key": "gpu_memory_utilization", "label": "GPU Memory Utilization", "type": "number", "default": 0.9},
        {"key": "dtype", "label": "Dtype", "type": "string", "default": "auto"},
        {"key": "port", "label": "Port", "type": "integer", "default": 8000},
    ],
    "ollama": [
        {"key": "host", "label": "Host", "type": "string", "default": "localhost"},
        {"key": "port", "label": "Port", "type": "integer", "default": 11434},
        {"key": "manage", "label": "Launch container", "type": "boolean", "default": True},
    ],
    "llamacpp": [
        {"key": "model_path", "label": "Model Path", "type": "string", "required": True},
        {"key": "context_length", "label": "Context Length", "type": "integer", "default": 4096},
        {"key": "gpu_layers", "label": "GPU Layers", "type": "integer", "default": 0},
    ],
    "openai_compatible": [
        {"key": "endpoint", "label": "Endpoint", "type": "string", "required": True},
        {"key": "api_key", "label": "API Key", "type": "secret"},
        {"key": "model", "label": "Model", "type": "string", "required": True},
    ],
}


@router.get("")
def list_providers():
    return {
        "types": available_provider_types(),
        "schemas": PROVIDER_CONFIG_SCHEMAS,
    }


@router.get("/{provider_type}/models")
def list_models(provider_type: str, request: Request, name: str = "probe"):
    """
    Probe a provider for its currently available models.

    Meaningful for providers that expose a catalog before you pick a model
    to run (Ollama's already-pulled models, an OpenAI-compatible API's
    `/models` listing). vLLM and llama.cpp serve exactly one model per
    running instance, decided at *launch* time, so there is nothing to list
    ahead of time for them -- the experiment builder simply takes a free-text
    model id / file path for those two (see PROVIDER_CONFIG_SCHEMAS above).

    Provider-specific connection options (host, port, endpoint, api_key,
    ...) are passed as query parameters and forwarded verbatim into the
    provider's options.
    """
    if provider_type in ("vllm", "llamacpp"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{provider_type}' serves a single model chosen at launch time; "
                "there is no catalog to list ahead of time. Enter the model "
                "id or file path directly."
            ),
        )
    options = {k: v for k, v in request.query_params.items() if k != "name"}
    try:
        provider = create_provider(
            ProviderConfig(name=name, type=provider_type, options=options)
        )
        return {"models": [m.__dict__ for m in provider.list_models()]}
    except (ProviderError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
