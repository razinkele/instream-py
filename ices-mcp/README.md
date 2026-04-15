# ICES Fish Data MCP Server

Model Context Protocol server providing AI assistants with comprehensive access to ICES fisheries data.

## Data Sources

| Service | Description | Auth |
|---------|-------------|------|
| **DATRAS** | Trawl survey data (hauls, length, age, CPUE, indices) | None |
| **SAG** | Stock Assessment Graphs (SSB, F, recruitment time-series) | None |
| **SID** | Stock Information Database (stock metadata) | None |
| **ICES Vocab** | Species codes (WoRMS Aphia IDs) | None |
| **ICES GIS** | Spatial layers (stat areas, rectangles, ecoregions) | None |

## Available Tools (21 total)

### DATRAS (9 tools)
- `datras_list_surveys` — list all survey acronyms
- `datras_survey_years` — years for a survey
- `datras_get_haul_data` — HH exchange data
- `datras_get_length_data` — HL length-frequency data
- `datras_get_age_data` — CA catch/age data
- `datras_get_cpue_length` — CPUE per length per haul per hour
- `datras_get_cpue_age` — CPUE per age per haul per hour
- `datras_get_indices` — age-based abundance indices
- `datras_get_catch_weight` — derived catch weight by species/haul
- `datras_get_species_list` — species recorded in DATRAS

### SAG (4 tools)
- `sag_list_stocks` — assessed stocks by year
- `sag_search_stocks` — search stocks by species
- `sag_get_stock_summary` — SSB/F/recruitment time-series
- `sag_get_reference_points` — Blim, Bpa, FMSY

### SID (2 tools)
- `sid_search_stocks` — search by species/label/expert group/ecoregion
- `sid_stocks_by_year` — all stocks for a year

### Vocabulary (1 tool)
- `ices_search_species` — search species by name → Aphia IDs

### GIS (4 tools)
- `ices_list_gis_layers` — available spatial layers
- `ices_get_areas` — ICES statistical areas (GeoJSON)
- `ices_get_rectangles` — stat rectangles by bbox
- `ices_get_gis_layer` — any ICES WFS layer

### Analysis (1 tool)
- `ices_analyse_distribution` — spatial/temporal distribution analysis

## Setup

### Prerequisites
- Python 3.10+
- `mcp` SDK (`pip install "mcp[cli]"`)
- `pandas`, `requests` (already in shiny env)

### DATRAS support (optional)
The `ices_datras` package from [marine-gis-tools](https://github.com/razinkele/marine-gis-tools) enables DATRAS tools. Either:

1. **Symlink/copy** the `ices_datras/` directory into `vendor/`:
   ```
   mklink /D vendor\ices_datras ..\..\..\..\marine-gis-tools\ices_datras
   ```

2. **Or** add the repo root to `PYTHONPATH`:
   ```
   set PYTHONPATH=C:\path\to\marine-gis-tools
   ```

### Running
```bash
micromamba run -n shiny python ices_mcp_server.py
```

## Integration

### GitHub Copilot CLI (`~/.github/copilot/mcp.json`)
```json
{
  "mcpServers": {
    "ices-fish-data": {
      "command": "micromamba",
      "args": ["run", "-n", "shiny", "python", "C:/path/to/ices-mcp/ices_mcp_server.py"],
      "env": {
        "PYTHONPATH": "C:/path/to/marine-gis-tools"
      }
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "ices-fish-data": {
      "command": "micromamba",
      "args": ["run", "-n", "shiny", "python", "C:/path/to/ices-mcp/ices_mcp_server.py"],
      "env": {
        "PYTHONPATH": "C:/path/to/marine-gis-tools"
      }
    }
  }
}
```

## Example Queries

> "What herring stocks does ICES assess in the Baltic?"
> → `sag_search_stocks("herring")` → `sag_get_stock_summary(key)`

> "Show me cod distribution in the North Sea IBTS survey for 2020-2023"
> → `ices_analyse_distribution("NS-IBTS", [2020,2021,2022,2023], [1,3], [126436])`

> "Get the ICES statistical rectangles covering the Lithuanian EEZ"
> → `ices_get_rectangles(19.0, 55.0, 22.0, 56.5)`
