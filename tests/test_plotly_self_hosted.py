"""Phase 3 Task 3.1: Plotly must be self-hosted, not loaded from CDN.

CDN loads are blocked by Edge/Firefox Tracking Prevention on the
laguna.ku.lt deploy, rendering all four plot panels empty. Must reference
a local copy under app/www/.
"""
from pathlib import Path


def test_plotly_js_is_bundled_in_www():
    """plotly-2.35.2.min.js must exist under app/www/ (served as a static asset)."""
    www = Path(__file__).parent.parent / "app" / "www"
    plotly = www / "plotly-2.35.2.min.js"
    assert plotly.exists(), (
        f"Expected self-hosted Plotly at {plotly}. CDN loads are blocked by "
        "Edge/Firefox tracking prevention on the laguna deploy."
    )
    assert plotly.stat().st_size > 1_000_000, (
        f"Plotly JS at {plotly} is suspiciously small "
        f"({plotly.stat().st_size} bytes) — download may have been truncated."
    )


def test_app_py_does_not_reference_plotly_cdn():
    """app/app.py must not load Plotly from cdn.plot.ly — that bypasses
    the self-hosted asset and re-enables tracking-prevention blocking."""
    app_py = Path(__file__).parent.parent / "app" / "app.py"
    text = app_py.read_text(encoding="utf-8")
    assert "cdn.plot.ly" not in text, (
        "app/app.py references cdn.plot.ly — must use the self-hosted "
        "plotly-2.35.2.min.js from app/www/ instead."
    )
    assert "plotly-2.35.2.min.js" in text, (
        "app/app.py does not load the self-hosted Plotly script."
    )
