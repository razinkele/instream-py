---
name: ices-data
description: Use when the user asks about ICES fisheries data, fish distribution, stock assessments, trawl surveys, DATRAS, SAG, SID, species lookups, ICES statistical areas/rectangles, or marine fish ecology in European waters. Triggers on "ICES", "fish stock", "DATRAS", "trawl survey", "stock assessment", "fish distribution", "ICES rectangles", "Baltic fish", "North Sea fish".
---

# ICES Fish Data — Analysis & Query Skill

Use the **ices-fish-data** MCP server tools to query ICES fisheries APIs. The server is at `ices-mcp/ices_mcp_server.py` in this repo and exposes 22 tools via stdio transport.

## Available MCP Tools

### DATRAS — Trawl Survey Data
| Tool | Purpose |
|------|---------|
| `datras_list_surveys` | List all survey acronyms (NS-IBTS, BITS, etc.) |
| `datras_survey_years` | Years available for a survey |
| `datras_get_haul_data` | HH haul-level exchange data |
| `datras_get_length_data` | HL length-frequency exchange data |
| `datras_get_age_data` | CA catch/age exchange data |
| `datras_get_cpue_length` | CPUE per length per haul per hour |
| `datras_get_cpue_age` | CPUE per age per haul per hour |
| `datras_get_indices` | Age-based abundance indices |
| `datras_get_catch_weight` | Derived catch weight by species/haul |
| `datras_get_species_list` | Species recorded in DATRAS |

### SAG — Stock Assessment Graphs
| Tool | Purpose |
|------|---------|
| `sag_list_stocks` | All assessed stocks for a given year |
| `sag_search_stocks` | Search stocks by species name |
| `sag_get_stock_summary` | SSB, F, recruitment, catches time-series |
| `sag_get_reference_points` | Blim, Bpa, FMSY reference points |

### SID — Stock Information Database
| Tool | Purpose |
|------|---------|
| `sid_search_stocks` | Search by species/label/expert group/ecoregion |
| `sid_stocks_by_year` | All stocks for a year |

### Vocabulary
| Tool | Purpose |
|------|---------|
| `ices_search_species` | Search species by name → WoRMS Aphia IDs |

### GIS — Spatial Reference Layers
| Tool | Purpose |
|------|---------|
| `ices_list_gis_layers` | Available spatial layers on ICES GeoServer |
| `ices_get_areas` | ICES statistical areas as GeoJSON |
| `ices_get_rectangles` | Stat rectangles by bounding box |
| `ices_get_gis_layer` | Any ICES WFS layer by name |

### Analysis
| Tool | Purpose |
|------|---------|
| `ices_analyse_distribution` | Spatial/temporal distribution analysis from DATRAS data |

## Common Workflows

### 1. Fish Distribution Analysis
```
1. datras_list_surveys → pick survey (e.g. "BITS" for Baltic, "NS-IBTS" for North Sea)
2. ices_search_species → get Aphia ID for target species
3. ices_analyse_distribution(survey, years, quarters, aphia_ids) → spatial stats
```

### 2. Stock Assessment Review
```
1. sag_search_stocks("cod") → find stock keys
2. sag_get_stock_summary(assessment_key) → SSB/F/R time-series
3. sag_get_reference_points(assessment_key) → Blim, FMSY
```

### 3. Survey Data Extraction
```
1. datras_survey_years("BITS") → available years
2. datras_get_haul_data("BITS", 2023, 1) → haul positions + conditions
3. datras_get_cpue_length("BITS", 2023, 1) → CPUE by species/length
```

### 4. Spatial Queries
```
1. ices_get_rectangles(19.0, 55.0, 22.0, 56.5) → rectangles in Lithuanian EEZ
2. ices_get_areas("27.3.d.24") → specific ICES subdivision polygon
```

## Key Species Aphia IDs (Baltic/North Sea)
- Atlantic cod: 126436
- Atlantic herring: 126417
- European sprat: 126425
- Atlantic salmon: 127186
- European flounder: 127141
- Turbot: 127149

## ICES Survey Codes
- **BITS** — Baltic International Trawl Survey
- **NS-IBTS** — North Sea International Bottom Trawl Survey
- **BIAS** — Baltic International Acoustic Survey
- **BTS** — Beam Trawl Survey
- **EVHOE** — French bottom trawl Bay of Biscay

## API Notes
- All ICES APIs are public, no authentication required
- DATRAS uses XML/SOAP, SAG and SID use JSON REST
- GIS uses OGC WFS 2.0.0 on `gis.ices.dk/geoserver/wfs`
- DATRAS tools require the `ices_datras` package from [marine-gis-tools](https://github.com/razinkele/marine-gis-tools)
- SAG, SID, Vocab, and GIS tools work without extra dependencies
