# Data needed to set up Salmopy for coastal Lithuania

A gap analysis of what real data is required to move the model from the
current `example_baltic` fixture (Nemunas-centric, Atlantic-salmon-parameterised,
**synthetic hydraulics**) to a defensible **coastal-Lithuania sea-trout** setup.

## Scope decision first

`example_baltic` is built around **Atlantic salmon (*Salmo salar*)** in the
**Nemunas/Curonian Lagoon** system. "Coastal Lithuania" is a different population:
the directly-Baltic-draining rivers are **sea-trout (*Salmo trutta trutta*)
dominated**, with only minor salmon. The three genetic stock units studied in
Lithuania are **Akmena-Danė, Bartuva, and Nemunas** (Bartuvienė/Kesminas work,
HELCOM BSEP 126B). So the first input gap is conceptual: decide species and rivers.

Suggested reach set for a coastal build (all drain straight to the Baltic, not via
the lagoon):

- **Akmena-Danė** (already stubbed as `Dane_Upper/Middle/Lower/Mouth` + `KlaipedaStrait`)
- **Šventoji** (the coastal river at Palanga, not the Nemunas-basin tributary)
- **Bartuva / Rąžė** (Šventoji-Liepāja system; Bartuva exits in Latvia — cross-border like Gilija)
- Optionally **Smeltalė** and other small Klaipėda-area streams

Everything below is keyed to the actual model inputs (the per-reach CSVs, the
shapefile, the species block, the marine block) so each item maps to a file you
have to produce.

---

## 1. Species parameterisation — sea trout (highest-value gap)

The `species:` block is currently `BalticAtlanticSalmon`. Sea trout differ in
bioenergetics, size-at-stage, spawning timing, fecundity and smolt age. You need
a `BalticSeaTrout` species block backed by:

| Parameter group | What to source | Source |
|---|---|---|
| Length-weight (`weight_A`, `weight_B`) | LT sea-trout L-W regression | National electrofishing dataset; FishBase |
| Fecundity (`spawn_fecund_mult/_exp`) | eggs vs female length for LT sea trout | Kesminas/Kontautas surveys |
| Spawn window (`spawn_start/end_day`) | LT redd-count timing (Oct–Dec) | Beaver-dam redd-count study (Šašuola/Plaštaka) |
| Emergence length, smolt min length | local parr/smolt size | electrofishing + smolt-trap length data |
| Smolt age structure | 1–3 yr smolt fractions (warmer/southern → younger) | HELCOM BSEP 126B LT chapter |
| Consumption/respiration (`cmax_*`, `resp_*`) | can be kept from inSTREAM trout defaults but should be flagged | Railsback inSTREAM trout params |

Without this, the run is "salmon in trout rivers" and is not credible for coastal LT.

## 2. River geometry — shapefile + per-cell habitat attributes

The mesh (`Shapefile/BalticExample.shp`) carries one polygon per habitat cell with
attributes the model reads via `spatial.gis_properties`:

- `ID_TEXT`, `REACH_NAME`, `AREA` — generated from geometry (OK to auto-build)
- `M_TO_ESC` (distance to escape cover), `NUM_HIDING` (hiding places),
  `FRACVSHL` (fraction velocity shelter), `FRACSPWN` (**fraction spawning gravel**)

**Needed real data:**

1. **Channel centrelines for Šventoji, Bartuva, Rąžė** — OSM via the existing
   `create_model_osm.py` pipeline (merge Lithuania + Latvia PBFs for Bartuva,
   exactly like Lithuania + Kaliningrad for Gilija). Geometry is free; this is low effort.
2. **Real channel widths / wetted area** per reach to replace the buffer-factor
   inflation — from the national hydrography layer (Upių georeferencinis tinklas)
   or orthophoto digitising at the [geoportal.lt](https://www.geoportal.lt) service.
3. **Spawning-gravel fraction (`FRACSPWN`) and hiding/shelter per cell** — this is
   the single most decision-relevant habitat field for trout and is currently
   synthetic. Source from **habitat surveys / electrofishing site descriptions**
   (substrate class, cover) used in the LT 0+ parr monitoring (≈ national sites).

## 3. Hydraulics — depth & velocity rating tables (currently synthetic)

Each reach needs `<Reach>-Depths.csv` and `<Reach>-Vels.csv`: a lookup of
**per-cell depth and velocity at N discharge levels** (the Baltic files use 10
flow columns). Today these are jitter around a published mean — explicitly flagged
as synthetic in `docs/case-studies/baltic-workflow.md` §8.

**Needed:**

- **Cross-section / depth–velocity rating** at gauged sections for Danė, Šventoji,
  Bartuva. Sources: LHMT hydrometric stations; or generate with a 1-D/2-D hydraulic
  model (HEC-RAS) from surveyed cross-sections + a DEM.
- **Channel-bed DEM / bathymetry for rivers** — EMODnet covers only marine cells;
  rivers need national survey data. Lidar DEM (national 1 m DTM at geoportal.lt)
  plus measured cross-sections is the realistic route.

## 4. Daily environmental time series (currently synthetic sinusoid + noise)

Each reach needs `<Reach>-TimeSeriesInputs.csv` with daily
`Date,temperature,flow,turbidity`.

| Variable | Real source | Notes |
|---|---|---|
| **Discharge (flow)** | **LHMT** hydrological stations (meteo.lt, 153 gauges) | Danė, Šventoji, Bartuva, Minija have gauges; need daily series over your sim window (2011→) |
| **Water temperature** | LHMT + national EPA (AAA) water-quality monitoring | Often gaps; may need air-temp regression infill |
| **Turbidity** | EPA (AAA) surface-water monitoring; or NTU↔TSS proxy | Sparsest variable — likely needs modelling from flow |

These are the backbone forcing; without real flow/temperature the population
dynamics are driven by a synthetic climate.

## 5. Initial population & recruitment

- `BalticExample-InitialPopulations.csv` — per reach × age class numbers and
  length ranges. Replace with **0+ / 1+ parr densities from LT electrofishing**
  (densities × wetted area). The national monitoring runs ~hundreds of sites; the
  Danė/Bartuva/Šventoji subset gives you real starting abundances.
- `pspc_smolts_per_year` per reach — **smolt production capacity**. Source from
  **smolt-trap counts** (LT operates trapping on monitored rivers) and HELCOM/ICES
  WGBAST river tables. Current Nemunas values are explicitly "order-of-magnitude placeholders".

## 6. Adult returns

`BalticExample-AdultArrivals.csv` — per year: number returning, sex ratio,
run-timing (start/peak/end), length distribution.

**Needed:** sea-trout **spawner counts / run timing** for Danė, Šventoji, Bartuva
— from redd counts, trap/weir counts, or fishery-independent surveys. Run timing
for sea trout differs from the salmon May–Aug window currently coded.

## 7. Marine domain (coastal transit + sea growth)

The `marine:` block uses monthly **temperature, salinity, prey index, predation
risk** per zone (Estuary/Coastal/Baltic Proper), all currently hand-set.

- **SE Baltic temperature & salinity** monthly climatology — Copernicus Marine /
  HELCOM / LHMT coastal stations (Klaipėda). Salinity here (~7 PSU) is roughly right
  but should be sourced.
- **Post-smolt / marine survival (SAR)** — `post_smolt_survival_baltic.csv` exists
  but is salmon-tuned; sea-trout coastal post-smolt survival is different and more
  local (trout stay near the coast). HELCOM RETROUT / WGBAST.
- **Grey-seal predation** (`grey_seal_abundance_baltic.csv`, Arc P) — HELCOM seal
  abundance; relevant since coastal sea trout are heavily seal/cormorant exposed.
- **Cormorant pressure** — not yet a model input but ecologically dominant for LT
  coastal trout; consider adding as a predation forcing (would need colony counts).

## 8. Calibration targets (to validate the build)

To calibrate/validate rather than just run, you need observation series:
0+ parr density time series, smolt counts, and adult/spawner counts per river —
the same LT monitoring datasets above, formatted like
`data/wgbast/observations/smolt_trap_counts.csv` and the `ParityTarget` workflow.

---

## Priority order (what to get first)

1. **Sea-trout species block** (§1) — without it the system is mis-specified.
2. **Real daily flow + water temperature** for Danė/Šventoji/Bartuva (§4) from LHMT — biggest realism gain per unit effort.
3. **0+ parr densities + smolt counts** (§5) for initial pop and PSPC.
4. **Spawning-gravel / habitat attributes** (§2.3) — drives trout habitat selection.
5. River geometry for the new coastal reaches (§2.1, easy via OSM).
6. Depth/velocity rating tables (§3) — highest-effort; can stay synthetic longest.
7. Adult returns + marine/seal forcing (§6, §7) — refine once freshwater side is real.

## Key Lithuanian data holders

- **LHMT** (Lietuvos hidrometeorologijos tarnyba, meteo.lt) — discharge, water temperature, 153 gauges
- **AAA** (Aplinkos apsaugos agentūra) — surface-water quality, turbidity, monitoring
- **Fisheries Service / Nature Research Centre (Gamtos tyrimų centras), Kesminas & Kontautas groups** — electrofishing, smolt traps, redd counts, genetics
- **geoportal.lt** — national DEM (lidar 1 m), hydrography layer, orthophotos
- **HELCOM BSEP 126B "Salmon and Sea Trout Populations and Rivers in Lithuania"** + ICES WGBAST — river tables, smolt production, stock units
- **Copernicus Marine / EMODnet** — SE Baltic T/S, marine bathymetry (already wired for marine cells)
