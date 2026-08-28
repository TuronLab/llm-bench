"""Concurrent streaming requests for measuring OpenAI-compatible model endpoints."""

from __future__ import annotations

import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from infrastructure.providers.base import Provider, ProviderError
from infrastructure.storage.schemas import LoadTestingConfig, LoadTestingResult
from core.runner.harness_runner import _resources, metric_provider_options


def run_load_testing_test(provider: Provider, model: str, config: LoadTestingConfig, users: int) -> LoadTestingResult:
    """Run a burst of concurrent streaming requests and summarize its performance."""
    endpoint = provider.endpoint().rstrip("/")
    if not endpoint:
        raise ProviderError("LoadTesting tests require a provider with an OpenAI-compatible HTTP endpoint")
    input_text = _load_input(config.input)

    total_requests = users * config.requests_per_user
    start_gate = threading.Event()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=users) as executor:
        futures = [
            executor.submit(_stream_request, provider, endpoint, model, config, input_text, start_gate)
            for _ in range(total_requests)
        ]
        start_gate.set()
        samples = [future.result() for future in as_completed(futures)]
    elapsed = time.monotonic() - started

    successful = [sample for sample in samples if sample["error"] is None]
    ttfts = [sample["ttft_seconds"] for sample in successful if sample["ttft_seconds"] is not None]
    latencies = [sample["latency_seconds"] for sample in successful]
    perceived_rates = [sample["perceived_tokens_per_second"] for sample in successful if sample["perceived_tokens_per_second"] is not None]
    output_tokens = sum(sample["output_tokens"] for sample in successful)
    estimated_tokens = any(sample["tokens_estimated"] for sample in successful)
    metrics = {
        "requests": total_requests,
        "successful_requests": len(successful),
        "failed_requests": total_requests - len(successful),
        "error_rate": (total_requests - len(successful)) / total_requests,
        "wall_time_seconds": elapsed,
        "ttft_mean_seconds": _mean(ttfts),
        "ttft_p50_seconds": _percentile(ttfts, 50),
        "ttft_p95_seconds": _percentile(ttfts, 95),
        "latency_mean_seconds": _mean(latencies),
        "latency_p50_seconds": _percentile(latencies, 50),
        "latency_p95_seconds": _percentile(latencies, 95),
        "output_tokens": output_tokens,
        "output_tokens_per_second": output_tokens / elapsed if elapsed else 0,
        "perceived_tokens_per_second_mean": _mean(perceived_rates),
        "perceived_tokens_per_second_p50": _percentile(perceived_rates, 50),
        "tokens_estimated": estimated_tokens,
        "errors": [sample["error"] for sample in samples if sample["error"]][:5],
    }
    safe_options = metric_provider_options(provider.config.options)
    options = provider.config.options
    device = options.get("device")
    if device is None:
        resources = _resources()
        device = resources.get("gpu") or resources.get("cpu") or "unknown"
    extra_conf = {"input": config.input}
    if safe_options:
        extra_conf["provider_options"] = safe_options
    return LoadTestingResult(
        model=model,
        provider=provider.config.name,
        users=users,
        input=config.input,
        max_output_tokens=config.max_output_tokens,
        requests_per_user=config.requests_per_user,
        provider_options=safe_options,
        metadata={
            "common": {key: value for key, value in {
                "device": device,
                "max_output_tokens": config.max_output_tokens,
                "requests_per_user": config.requests_per_user,
                "temperature": config.temperature,
                "timeout_seconds": config.timeout_seconds,
            }.items() if value not in {0, 1, 128, 120}},
            "extra_conf": extra_conf,
            "resources": _resources(),
        },
        metrics=metrics,
    )


def _load_input(value: str) -> str:
    """Return literal text or the UTF-8 contents of a ``file://`` URI."""
    if not value.startswith("file://"):
        return value
    parsed = urlparse(value)
    path_value = unquote(parsed.path)
    if parsed.netloc in (".", ".."):
        path_value = f"{parsed.netloc}{parsed.path}"
    elif parsed.netloc and parsed.netloc != "localhost":
        path_value = f"//{parsed.netloc}{path_value}"
    path = Path(path_value)
    if path.suffix.lower() not in {".txt", ".md"}:
        raise ProviderError(f"LoadTesting input file must be .txt or .md: '{path}'")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProviderError(f"Could not read load_testing input file '{path}': {exc}") from exc


def _stream_request(provider: Provider, endpoint: str, model: str, config: LoadTestingConfig, input_text: str, start_gate: threading.Event) -> dict[str, Any]:
    start_gate.wait()
    headers = {"Authorization": f"Bearer {provider.api_key()}"} if provider.api_key() else {}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": input_text}],
        "max_tokens": config.max_output_tokens,
        "temperature": config.temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    started = time.monotonic()
    first_token_at = None
    text = ""
    usage_tokens = None
    try:
        with httpx.stream("POST", f"{endpoint}/chat/completions", headers=headers, json=payload, timeout=config.timeout_seconds) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                usage = event.get("usage") or {}
                usage_tokens = usage.get("completion_tokens", usage_tokens)
                for choice in event.get("choices", []):
                    content = (choice.get("delta") or {}).get("content")
                    if content:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                        text += content
        finished = time.monotonic()
        token_count = usage_tokens if isinstance(usage_tokens, int) else len(text.split())
        generation_seconds = finished - first_token_at if first_token_at else None
        return {"ttft_seconds": first_token_at - started if first_token_at else None, "latency_seconds": finished - started, "output_tokens": token_count, "perceived_tokens_per_second": token_count / generation_seconds if generation_seconds else None, "tokens_estimated": usage_tokens is None, "error": None}
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        return {"ttft_seconds": None, "latency_seconds": time.monotonic() - started, "output_tokens": 0, "perceived_tokens_per_second": None, "tokens_estimated": False, "error": str(exc)}


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile / 100
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
