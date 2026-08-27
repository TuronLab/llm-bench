"""Local Hugging Face Transformers provider backed by lm-evaluation-harness."""

from __future__ import annotations

from infrastructure.providers.base import ModelInfo, Provider, ProviderStatus


class HuggingFaceProvider(Provider):
    """Run a Transformers model locally through lm-eval's ``hf`` backend."""

    def start(self) -> None:
        self.status = ProviderStatus.READY

    def stop(self) -> None:
        self.status = ProviderStatus.STOPPED

    def _health_check(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        model = self.config.options.get("model")
        return [ModelInfo(id=model, name=model)] if model else []

    def endpoint(self) -> str:
        # Local hf runs do not expose an HTTP endpoint.
        return ""

    def harness_model_type(self) -> str:
        return "hf"

    def harness_model_args(self, model: str) -> str:
        opts = self.config.options
        args = {"pretrained": model}
        for key in ("device", "dtype", "batch_size", "trust_remote_code", "revision"):
            if key in opts:
                args[key] = opts[key]
        return ",".join(f"{key}={value}" for key, value in args.items())
