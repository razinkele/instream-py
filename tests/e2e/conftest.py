"""E2E test configuration.

The Shiny app must be running for these tests. Start it separately
(e.g. `micromamba run -n shiny shiny run app/app.py --port 8000`) and
point the suite at it via the E2E_BASE_URL env var.

We deliberately do NOT spawn the app from a fixture: on Windows + OneDrive,
`shiny run --reload` zombie-processes are a known issue (see CLAUDE.md),
and test runs have no business racing a user-facing dev server.
"""

import os
import socket

import pytest

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _base_url() -> str:
    url = os.environ.get("E2E_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    return url


def _app_reachable(url: str, timeout: float = 1.0) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def base_url() -> str:
    url = _base_url()
    if not _app_reachable(url):
        pytest.skip(
            f"Shiny app not reachable at {url}. "
            "Start it with `micromamba run -n shiny shiny run app/app.py --port 8000` "
            "or set E2E_BASE_URL.",
            allow_module_level=False,
        )
    return url


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
        "ignore_https_errors": True,
    }
