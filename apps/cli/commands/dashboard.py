from __future__ import annotations

import os
import webbrowser

from apps.cli.client import console


def open_dashboard():
    """Open the web dashboard in your default browser."""
    url = os.environ.get("BENCHLAB_WEB_URL", "http://localhost:3000")
    console.print(f"Opening dashboard at [bold cyan]{url}[/bold cyan]")
    webbrowser.open(url)
