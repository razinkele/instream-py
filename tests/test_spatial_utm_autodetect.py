"""Phase 3 Task 3.2: spatial_panel must auto-detect UTM zone, not hardcode
UTM 34N (Baltic-only). Non-Baltic meshes (Chinook example_a in UTM 10,
North Sea in UTM 31, etc.) previously silently projected through UTM 34N,
producing centroids shifted by hundreds of km.
"""
import inspect
from pathlib import Path


def test_spatial_panel_uses_estimate_utm_crs():
    """Source-level guard: spatial_panel.py must call estimate_utm_crs
    rather than hardcoding epsg=32634 at the centroid reprojection site."""
    src = (Path(__file__).parent.parent / "app" / "modules" / "spatial_panel.py"
           ).read_text(encoding="utf-8")
    # Locate the centroid reprojection block
    idx = src.find("centroids_utm = ")
    assert idx > 0, "Expected centroid reprojection block not found"
    window = src[max(0, idx - 500):idx]
    assert "estimate_utm_crs" in window, (
        "spatial_panel.py centroid reprojection must use cells.estimate_utm_crs() "
        "to auto-detect the UTM zone. Hardcoding epsg=32634 (UTM 34N) silently "
        "corrupts centroids for non-Baltic meshes."
    )
