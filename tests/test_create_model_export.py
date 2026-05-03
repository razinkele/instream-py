"""Tests for create_model_export."""
import sys
from pathlib import Path
import pytest

pytest.importorskip("shiny")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

# v0.49.0: imports for the round-trip regression test below.
np = pytest.importorskip("numpy")
gpd = pytest.importorskip("geopandas")
pd = pytest.importorskip("pandas")
shapely_geometry = pytest.importorskip("shapely.geometry")
Polygon = shapely_geometry.Polygon

from modules.create_model_export import export_template_csvs
from modules.create_model_utils import TEMPLATE_FLOWS  # canonical home
from salmopy.io.hydraulics_reader import _parse_hydraulic_csv


def test_export_yaml_respects_junction_ids():
    from modules.create_model_export import export_yaml
    import yaml

    reaches = {
        "reach_A": {
            "segments": [], "properties": [], "color": [255, 0, 0, 255],
            "type": "river", "upstream_junction": 10, "downstream_junction": 20,
        },
        "reach_B": {
            "segments": [], "properties": [], "color": [0, 255, 0, 255],
            "type": "river", "upstream_junction": 20, "downstream_junction": 30,
        },
    }
    yaml_str = export_yaml(reaches=reaches)
    config = yaml.safe_load(yaml_str)
    assert config["reaches"]["reach_A"]["upstream_junction"] == 10
    assert config["reaches"]["reach_A"]["downstream_junction"] == 20
    assert config["reaches"]["reach_B"]["upstream_junction"] == 20
    assert config["reaches"]["reach_B"]["downstream_junction"] == 30


def test_export_yaml_fallback_sequential_junctions():
    from modules.create_model_export import export_yaml
    import yaml

    reaches = {
        "reach_X": {
            "segments": [], "properties": [], "color": [255, 0, 0, 255],
            "type": "river",
        },
    }
    yaml_str = export_yaml(reaches=reaches)
    config = yaml.safe_load(yaml_str)
    assert config["reaches"]["reach_X"]["upstream_junction"] == 1
    assert config["reaches"]["reach_X"]["downstream_junction"] == 2


def test_export_template_csvs_round_trips_through_hydraulic_reader(tmp_path):
    """Round-trip: export 3-cell template → load via _parse_hydraulic_csv.

    This is the test that, when missing pre-v0.49, allowed the format
    mismatch (loader expects transposed matrix + comment+count+flow-values
    header; export emitted flow-as-row + cells-as-columns + no header)
    to ship undetected since v0.30.x. Locking it in.
    """
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["C0001", "C0002", "C0003"],
            "reach_name": ["R1", "R1", "R1"],
        },
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]) for _ in range(3)],
        crs="EPSG:4326",
    )

    paths = export_template_csvs(
        reaches={"R1": {}},
        cells_gdf=cells,
        output_dir=tmp_path,
        start_date="2026-04-26",
    )

    depths_path = tmp_path / "R1-Depths.csv"
    vels_path = tmp_path / "R1-Vels.csv"
    ts_path = tmp_path / "R1-TimeSeriesInputs.csv"
    assert depths_path in paths
    assert vels_path in paths
    assert ts_path in paths

    # Round-trip Depths
    flows, depths, cids = _parse_hydraulic_csv(depths_path, return_cell_ids=True)
    assert flows.shape == (10,)
    assert depths.shape == (3, 10)
    assert cids == ["C0001", "C0002", "C0003"]
    # Lock in the TEMPLATE_FLOWS contract — guards against accidental
    # changes to the flow grid that would silently break downstream callers.
    assert list(flows) == pytest.approx(TEMPLATE_FLOWS)
    # Sanity: the depth matrix must contain SOME variation. Guaranteed by
    # the formula `(0.3 + 0.7 * log(flow/0.5+1)/log(1001)) * cell_var`:
    # base(flow) is monotonic in flow, so depths[c, 0] != depths[c, -1] for
    # ANY cell c regardless of cell_var. This avoids relying on Python's
    # randomized string-hash for cell_var-driven inter-cell variation.
    assert not np.all(depths == depths[0, 0])

    # Round-trip Vels
    flows_v, vels, cids_v = _parse_hydraulic_csv(vels_path, return_cell_ids=True)
    assert flows_v.shape == (10,)
    assert vels.shape == (3, 10)
    assert cids_v == ["C0001", "C0002", "C0003"]
    assert list(flows_v) == pytest.approx(TEMPLATE_FLOWS)
    assert not np.all(vels == vels[0, 0])

    # Round-trip TimeSeriesInputs (pandas-loadable, separate format from
    # the hydraulic CSVs but worth a smoke check while we're here).
    ts = pd.read_csv(ts_path)
    assert len(ts) == 365
    assert set(ts.columns) >= {"date", "flow", "temperature", "turbidity"}


def test_export_yaml_latitude_from_cells_centroid():
    """v0.57.0 fix #5: export_yaml derives light.latitude from cells centroid.

    Pre-fix bug: every exported model got hardcoded latitude=55.7 (Curonian
    Lagoon), so a Norwegian model would receive Lithuanian photoperiod.
    Fix: when cells_gdf is provided, latitude is the mean centroid y in
    EPSG:4326. Without cells_gdf, latitude falls back to the previous default.
    """
    import yaml as _yaml

    # Build a 3-cell fixture sitting at ~69°N (Norway, well outside 55.7°N).
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["C0001", "C0002", "C0003"],
            "reach_name": ["R1", "R1", "R1"],
        },
        geometry=[
            Polygon([(20.0, 69.0), (20.001, 69.0), (20.001, 69.001), (20.0, 69.001)]),
            Polygon([(20.001, 69.0), (20.002, 69.0), (20.002, 69.001), (20.001, 69.001)]),
            Polygon([(20.002, 69.0), (20.003, 69.0), (20.003, 69.001), (20.002, 69.001)]),
        ],
        crs="EPSG:4326",
    )

    from modules.create_model_export import export_yaml
    yaml_str = export_yaml(reaches={"R1": {}}, cells_gdf=cells)
    config = _yaml.safe_load(yaml_str)

    # Centroid of unit squares at y ∈ [69.0, 69.001] is ~69.0005°N.
    assert 68.9 < config["light"]["latitude"] < 69.1, (
        f"expected ~69°N, got {config['light']['latitude']}"
    )

    # No-cells fallback keeps the previous behaviour so existing callers
    # that pass cells_gdf=None do not silently change.
    yaml_str_no_cells = export_yaml(reaches={"R1": {}}, cells_gdf=None)
    config_no_cells = _yaml.safe_load(yaml_str_no_cells)
    assert config_no_cells["light"]["latitude"] == 55.7

    # Geometry-less GeoDataFrame fallback — guards the call shape used by
    # tests/test_create_model.py::test_export_yaml_has_reaches which
    # constructs `gpd.GeoDataFrame({"cell_id": [...]})` with no geometry
    # column. Pre-guard, _derive_latitude raised on .geometry.centroid;
    # post-guard it returns the 55.7 default unchanged.
    geomless = gpd.GeoDataFrame({"cell_id": ["C0001"], "reach_name": ["R1"]})
    yaml_str_geomless = export_yaml(reaches={"R1": {}}, cells_gdf=geomless)
    config_geomless = _yaml.safe_load(yaml_str_geomless)
    assert config_geomless["light"]["latitude"] == 55.7
