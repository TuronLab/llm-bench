"""Shared HTTP client for talking to the backend REST API from the CLI."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from rich.console import Console

console = Console()
error_console = Console(stderr=True, style="bold red")

API_BASE_URL = os.environ.get("BENCHLAB_API_URL", "http://localhost:8000/api/v1")


class ApiClient:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def _handle(self, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:  # noqa: BLE001
                detail = response.text
            error_console.print(f"API error ({response.status_code}): {detail}")
            raise typer_exit()
        return response.json()

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        with httpx.Client(timeout=30.0) as client:
            return self._handle(client.get(f"{self.base_url}{path}", params=params))

    def post(self, path: str, json: Optional[dict] = None) -> Any:
        with httpx.Client(timeout=30.0) as client:
            return self._handle(client.post(f"{self.base_url}{path}", json=json))


def typer_exit():
    import typer

    return typer.Exit(code=1)


client = ApiClient()
