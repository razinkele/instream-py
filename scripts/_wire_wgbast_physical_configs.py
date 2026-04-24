"""Wire the 4 WGBAST river configs + CSVs to the new physical-domain shapefiles.

Companion to `_generate_wgbast_physical_domains.py`. The generator produces
shapefiles with 4 reaches (Mouth / Lower / Middle / Upper) per river, replacing
the Nemunas-basin names inherited from the template. This script:

  1. Replaces each config's `reaches:` section with 4 new entries matching
     the shapefile's REACH_NAME values. Hydrology parameters are derived
     from the existing Nemunas-basin reaches (most-similar-character mapping).
  2. Copies per-reach CSVs (TimeSeriesInputs / Depths / Vels) from the old
     Nemunas-basin names to the new Mouth/Lower/Middle/Upper names, preserving
     the per-river T/Q offsets already applied by `_scaffold_wgbast_rivers.py`.
  3. Updates `spatial.mesh_file` to the new shapefile path.
  4. Sets PSPC per reach so the river total matches WGBAST's assessment value.

WGBAST PSPC totals (smolts/year):
  Tornionjoki  2_200_000
  Simojoki       65_000
  Byskealven     30_000
  Morrumsan      90_000
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


# (short_name, TemplateStem, pspc_total, legacy_marine_reach_list)
RIVERS = [
    ("example_tornionjoki", "TornionjokiExample", 2_200_000),
    ("example_simojoki",    "SimojokiExample",       65_000),
    ("example_byskealven",  "ByskealvenExample",     30_000),
    ("example_morrumsan",   "MorrumsanExample",      90_000),
]


# New reach definitions. Map Mouth / Lower / Middle / Upper to a prototype
# Nemunas-basin reach whose hydrology character is most-similar-matching
# (e.g. 'Mouth' = broad slow water near sea → Nemunas estuary profile).
# This lets us reuse published depth/velocity curves instead of
# hand-authoring them from scratch.
REACH_PROTOTYPE = {
    "Mouth":  "Nemunas",   # broad, slow, downstream
    "Lower":  "Atmata",    # lower-tributary character
    "Middle": "Minija",    # mid-basin
    "Upper":  "Sysa",      # upper, smaller
}

# PSPC weights per reach (must sum to 1.0). Salmon redds sit mostly in
# mid-upper riffles; mouth gets 0.
PSPC_WEIGHT = {
    "Mouth":  0.00,
    "Lower":  0.30,
    "Middle": 0.45,
    "Upper":  0.25,
}

# Upstream/downstream junction topology: linear chain
#    (1) Mouth ← (2) Lower ← (3) Middle ← (4) Upper ← (5) (sea/source)
JUNCTIONS = {
    "Mouth":  (1, 2),
    "Lower":  (2, 3),
    "Middle": (3, 4),
    "Upper":  (4, 5),
}


def rewrite_config(cfg_path: Path, stem: str, pspc_total: int) -> None:
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 1. Point spatial.mesh_file at the new shapefile
    cfg["spatial"]["mesh_file"] = f"Shapefile/{stem}.shp"

    old_reaches = cfg["reaches"]

    # Idempotency: if already rewritten (has Mouth/Lower/Middle/Upper and no
    # prototype Nemunas-basin names), skip the reach rewrite. The shapefile
    # path and CSV-copy steps still run.
    already_rewritten = (
        all(n in old_reaches for n in REACH_PROTOTYPE)
        and "Nemunas" not in old_reaches
    )
    if already_rewritten:
        # Just make sure mesh_file is correct, which we did above, then
        # write back and return.
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(
                f"# {stem.replace('Example', '')} — physical-geography domain (v0.45).\n"
                "# 4 reaches (Mouth/Lower/Middle/Upper) along the real river\n"
                "# centerline. Shapefile generated via\n"
                "# scripts/_generate_wgbast_physical_domains.py.\n"
                "#\n"
            )
            yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)
        return

    river_name = old_reaches.get("Nemunas", {}).get("river_name", "")
    # Prefer filename-stem match for river_name if possible
    if not river_name:
        river_name = stem.replace("Example", "")

    # 2. Build new reaches from prototypes, preserving species-relevant params
    new_reaches = {}

    for new_name, proto in REACH_PROTOTYPE.items():
        if proto not in old_reaches:
            raise KeyError(
                f"{cfg_path.name}: expected prototype reach '{proto}' not found "
                f"(available: {sorted(old_reaches)})"
            )
        proto_entry = dict(old_reaches[proto])

        # Override reach-specific fields
        pspc_share = int(round(pspc_total * PSPC_WEIGHT[new_name]))
        if pspc_share > 0:
            proto_entry["pspc_smolts_per_year"] = pspc_share
        else:
            proto_entry.pop("pspc_smolts_per_year", None)

        ups, dns = JUNCTIONS[new_name]
        proto_entry["upstream_junction"] = ups
        proto_entry["downstream_junction"] = dns

        proto_entry["time_series_input_file"] = f"{new_name}-TimeSeriesInputs.csv"
        proto_entry["depth_file"] = f"{new_name}-Depths.csv"
        proto_entry["velocity_file"] = f"{new_name}-Vels.csv"
        proto_entry["river_name"] = river_name

        new_reaches[new_name] = proto_entry

    # Preserve marine-zone reaches (CuronianLagoon, BalticCoast etc.) unchanged.
    for name, entry in old_reaches.items():
        if name in REACH_PROTOTYPE.values() or name in REACH_PROTOTYPE:
            continue
        # non-prototype, non-new → likely marine zone. Keep.
        new_reaches[name] = entry

    cfg["reaches"] = new_reaches

    # 3. Write back, preserving only the YAML structure (comments lost; a
    # header line is prepended below to replace the old scaffold preamble).
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(
            f"# {river_name} — physical-geography domain (v0.45).\n"
            "# 4 reaches (Mouth/Lower/Middle/Upper) along the real river\n"
            "# centerline. Shapefile generated via\n"
            "# scripts/_generate_wgbast_physical_domains.py.\n"
            "# Hydrology parameters inherit from prototype Nemunas-basin reaches\n"
            "# (mapping: Mouth=Nemunas, Lower=Atmata, Middle=Minija, Upper=Sysa).\n"
            "# Per-reach TimeSeriesInputs carry the scaffolded T/Q offset\n"
            "# from _scaffold_wgbast_rivers.py.\n"
            "#\n"
        )
        yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)


def copy_reach_csvs(short_name: str, stem: str) -> None:
    """Write per-reach CSVs matching the new shapefile's cell counts.

    TimeSeriesInputs.csv is reach-scoped (not per-cell) — a straight copy
    preserves the scaffolded per-river T/Q offsets.

    Depths.csv and Vels.csv are per-cell, one row per cell. Since the
    new physical shapefile has N cells per reach (typically ~1000),
    we replicate the prototype's per-flow depth/velocity profile to all
    N cells. This preserves the published channel-mean hydraulics while
    matching the new cell-count contract required by the loader.
    """
    import geopandas as gpd

    fixture_dir = ROOT / "tests" / "fixtures" / short_name
    shp_path = fixture_dir / "Shapefile" / f"{stem}.shp"
    if not shp_path.exists():
        raise FileNotFoundError(
            f"{short_name}: shapefile not found: run "
            "_generate_wgbast_physical_domains.py first"
        )

    cells = gpd.read_file(shp_path)
    reach_cell_counts = cells["REACH_NAME"].value_counts().to_dict()

    for new_name, proto in REACH_PROTOTYPE.items():
        # TimeSeriesInputs: reach-scoped, copy verbatim (preserves T/Q)
        src_ts = fixture_dir / f"{proto}-TimeSeriesInputs.csv"
        dst_ts = fixture_dir / f"{new_name}-TimeSeriesInputs.csv"
        if not src_ts.exists():
            raise FileNotFoundError(
                f"{short_name}: prototype CSV missing: {src_ts.name}"
            )
        shutil.copy2(src_ts, dst_ts)

        # Depths / Vels: per-cell, regenerate to match new cell count
        n_new = reach_cell_counts.get(new_name, 0)
        if n_new == 0:
            raise RuntimeError(
                f"{short_name}: reach '{new_name}' has 0 cells in shapefile"
            )
        for suffix in ("Depths", "Vels"):
            src = fixture_dir / f"{proto}-{suffix}.csv"
            dst = fixture_dir / f"{new_name}-{suffix}.csv"
            _expand_per_cell_csv(src, dst, n_new)


def _expand_per_cell_csv(src: Path, dst: Path, n_cells: int) -> None:
    """Read a prototype Depths/Vels CSV, expand its data rows to n_cells.

    Format contract (from example_baltic Nemunas-Depths.csv):
      Lines 1..k-1: ';'-prefixed comments
      Line k    : "N,Number of flows in table,..." metadata
      Line k+1  : per-flow header "1.0,2.0,4.0,..."
      Line k+2+ : one row per cell — "index,d(f1),d(f2),...,d(fN)"

    We preserve the header block verbatim, then repeat the first data row
    n_cells times (with the row index updated to match). This keeps the
    published channel-mean hydraulics for every new cell, which is
    physically coarse but consistent with the scaffolding's synthetic
    label.
    """
    with open(src, encoding="utf-8") as f:
        lines = f.read().splitlines()

    # Find the first data row (starts with a bare integer followed by ',')
    header_end = None
    for i, line in enumerate(lines):
        parts = line.split(",")
        if not parts:
            continue
        first = parts[0].strip()
        if first.isdigit() and len(parts) > 1:
            # Could be metadata ("10,Number of flows...") or data ("1,0.3,0.4,...")
            # Metadata has text in column 2; data has numbers.
            try:
                float(parts[1])
                header_end = i
                break
            except ValueError:
                continue
    if header_end is None:
        raise RuntimeError(f"{src.name}: could not locate first data row")

    header_lines = lines[:header_end]
    template = lines[header_end].split(",")
    # Column 0 is the row index; columns 1+ are per-flow values
    payload = template[1:]

    with open(dst, "w", encoding="utf-8") as f:
        for hl in header_lines:
            f.write(hl + "\n")
        for i in range(n_cells):
            f.write(f"{i + 1}," + ",".join(payload) + "\n")


def main():
    for short_name, stem, pspc_total in RIVERS:
        cfg_path = ROOT / "configs" / f"{short_name}.yaml"
        print(f"[{short_name}] rewriting {cfg_path.name}...")
        rewrite_config(cfg_path, stem, pspc_total)
        print(f"[{short_name}] rewriting per-cell CSVs to match shapefile...")
        copy_reach_csvs(short_name, stem)
    print("Done.")


if __name__ == "__main__":
    main()
