# Marine Domain Scaffolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fish can leave freshwater as smolts, traverse marine zones, and return as spawning adults — with placeholder ecology (100% marine survival).

**Architecture:** Add 5 marine fields to TroutState, create MarineDomain class with ZoneState + StaticDriver, add zone_idx guards to 10 freshwater loops, implement smoltification/zone-migration/adult-return transitions, integrate via domain-dispatched step() in model.py.

**Tech Stack:** Python 3.11+, NumPy, Pydantic, pytest, micromamba env "shiny"

**Spec:** `docs/superpowers/specs/2026-04-10-marine-scaffolding-design.md`

---

## File Map

### New files
- `src/instream/marine/__init__.py` — package exports
- `src/instream/marine/domain.py` — MarineDomain, ZoneState, StaticDriver, transition functions
- `src/instream/marine/config.py` — MarineConfig, ZoneConfig Pydantic models
- `configs/example_marine.yaml` — Example A + marine section
- `tests/test_marine.py` — unit tests for marine domain
- `tests/test_marine_e2e.py` — end-to-end lifecycle test

### Modified files
- `src/instream/state/trout_state.py` — 5 new fields + zeros() update
- `src/instream/io/config.py` — `marine: Optional[MarineConfig]` in ModelConfig
- `src/instream/model.py` — freshwater_alive mask, marine step, smolt readiness, adult return
- `src/instream/model_environment.py` — cache _day_length, marine survival exclusion
- `src/instream/model_day_boundary.py` — freshwater guards on 5 alive-fish loops
- `src/instream/modules/migration.py` — smolt transition at river mouth
- `src/instream/modules/spawning.py` — set natal_reach_idx on emergence

---

## Task 1: TroutState Marine Fields

**Files:**
- Modify: `src/instream/state/trout_state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_state.py`:

```python
class TestTroutStateMarineFields:
    def test_zeros_has_zone_idx(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(10)
        assert ts.zone_idx.shape == (10,)
        assert ts.zone_idx.dtype == np.int32
        assert np.all(ts.zone_idx == -1)

    def test_zeros_has_sea_winters(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(10)
        assert ts.sea_winters.shape == (10,)
        assert np.all(ts.sea_winters == 0)

    def test_zeros_has_smolt_date(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(10)
        assert ts.smolt_date.shape == (10,)
        assert np.all(ts.smolt_date == -1)

    def test_zeros_has_natal_reach_idx(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(10)
        assert ts.natal_reach_idx.shape == (10,)
        assert np.all(ts.natal_reach_idx == -1)

    def test_zeros_has_smolt_readiness(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(10)
        assert ts.smolt_readiness.shape == (10,)
        assert ts.smolt_readiness.dtype == np.float64
        assert np.all(ts.smolt_readiness == 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_state.py::TestTroutStateMarineFields -v
```

Expected: FAIL — `TroutState` has no attribute `zone_idx`.

- [ ] **Step 3: Add 5 fields to TroutState dataclass and zeros()**

In `src/instream/state/trout_state.py`, add after `cmax_wt_term`:

```python
    # Marine domain fields
    zone_idx: np.ndarray         # int32, -1=freshwater, 0+=marine zone
    sea_winters: np.ndarray      # int32
    smolt_date: np.ndarray       # int32, ordinal date (-1=never)
    natal_reach_idx: np.ndarray  # int32, birth reach (-1=unset)
    smolt_readiness: np.ndarray  # float64, 0-1
```

In `zeros()`, add after the `cmax_wt_term` line:

```python
            zone_idx=np.full(capacity, -1, dtype=np.int32),
            sea_winters=np.zeros(capacity, dtype=np.int32),
            smolt_date=np.full(capacity, -1, dtype=np.int32),
            natal_reach_idx=np.full(capacity, -1, dtype=np.int32),
            smolt_readiness=np.zeros(capacity, dtype=np.float64),
```

- [ ] **Step 4: Run test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_state.py -v --tb=short
```

Expected: all state tests pass.

- [ ] **Step 5: Run full suite to check no regressions**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py -x
```

Expected: 729+ passed.

- [ ] **Step 6: Commit**

```bash
git add src/instream/state/trout_state.py tests/test_state.py
git commit -m "feat: add 5 marine fields to TroutState (zone_idx, sea_winters, smolt_date, natal_reach_idx, smolt_readiness)"
```

---

## Task 2: MarineConfig Pydantic Models

**Files:**
- Create: `src/instream/marine/__init__.py`
- Create: `src/instream/marine/config.py`
- Modify: `src/instream/io/config.py`
- Test: `tests/test_marine.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_marine.py`:

```python
"""Tests for marine domain scaffolding."""
import pytest
import numpy as np


class TestMarineConfig:
    def test_marine_config_loads_from_dict(self):
        from instream.marine.config import MarineConfig
        cfg = MarineConfig(**{
            "zones": [
                {"name": "Estuary", "area_km2": 50},
                {"name": "Coastal", "area_km2": 500},
            ],
            "zone_connectivity": [[0, 1]],
            "smolt_min_length": 12.0,
            "smolt_readiness_threshold": 0.8,
            "smolt_photoperiod_weight": 0.6,
            "smolt_temperature_weight": 0.4,
            "smolt_temperature_optimal": 10.0,
            "smolt_window_start_doy": 90,
            "smolt_window_end_doy": 180,
            "return_sea_winters": 2,
            "return_condition_min": 0.0,
            "static_driver": {
                "Estuary": {
                    "temperature": [5]*12,
                    "salinity": [5]*12,
                    "prey_index": [0.5]*12,
                    "predation_risk": [0.1]*12,
                },
                "Coastal": {
                    "temperature": [8]*12,
                    "salinity": [7]*12,
                    "prey_index": [0.6]*12,
                    "predation_risk": [0.05]*12,
                },
            },
        })
        assert len(cfg.zones) == 2
        assert cfg.zones[0].name == "Estuary"
        assert cfg.smolt_min_length == 12.0

    def test_model_config_accepts_marine(self):
        from instream.io.config import ModelConfig
        cfg = ModelConfig(
            simulation={"start_date": "2011-04-01", "end_date": "2011-05-01"},
            marine=None,
        )
        assert cfg.marine is None

    def test_model_config_without_marine_key(self):
        from instream.io.config import ModelConfig
        cfg = ModelConfig(
            simulation={"start_date": "2011-04-01", "end_date": "2011-05-01"},
        )
        assert cfg.marine is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_marine.py::TestMarineConfig -v
```

Expected: FAIL — `No module named 'instream.marine'`.

- [ ] **Step 3: Create marine package and config**

Create `src/instream/marine/__init__.py`:

```python
"""Marine domain for inSALMON anadromous lifecycle."""
```

Create `src/instream/marine/config.py`:

```python
"""Marine configuration — Pydantic models for zone setup and drivers."""
from typing import Dict, List, Optional
from pydantic import BaseModel


class ZoneConfig(BaseModel):
    name: str
    area_km2: float


class ZoneDriverData(BaseModel):
    temperature: List[float]  # 12 monthly values
    salinity: List[float]
    prey_index: List[float]
    predation_risk: List[float]


class MarineConfig(BaseModel):
    zones: List[ZoneConfig]
    zone_connectivity: List[List[int]]  # directed edges [[from, to], ...]
    smolt_min_length: float = 12.0
    smolt_readiness_threshold: float = 0.8
    smolt_photoperiod_weight: float = 0.6
    smolt_temperature_weight: float = 0.4
    smolt_temperature_optimal: float = 10.0
    smolt_window_start_doy: int = 90
    smolt_window_end_doy: int = 180
    return_sea_winters: int = 2
    return_condition_min: float = 0.0
    static_driver: Dict[str, ZoneDriverData] = {}
```

Add to `src/instream/io/config.py` ModelConfig:

```python
from typing import Optional
from instream.marine.config import MarineConfig

class ModelConfig(BaseModel):
    simulation: SimulationConfig
    performance: PerformanceConfig = PerformanceConfig()
    spatial: SpatialConfig = SpatialConfig()
    light: LightConfig = LightConfig()
    species: Dict[str, SpeciesConfig] = {}
    reaches: Dict[str, ReachConfig] = {}
    marine: Optional[MarineConfig] = None
```

- [ ] **Step 4: Run tests**

```bash
micromamba run -n shiny python -m pytest tests/test_marine.py::TestMarineConfig tests/test_config.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/instream/marine/ src/instream/io/config.py tests/test_marine.py
git commit -m "feat: add MarineConfig Pydantic models and marine package"
```

---

## Task 3: ZoneState and StaticDriver

**Files:**
- Modify: `src/instream/marine/domain.py`
- Test: `tests/test_marine.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_marine.py`:

```python
class TestZoneState:
    def test_zone_state_creation(self):
        from instream.marine.domain import ZoneState
        zs = ZoneState.zeros(3, names=["Estuary", "Coastal", "Baltic"])
        assert zs.num_zones == 3
        assert zs.temperature.shape == (3,)
        assert zs.name[0] == "Estuary"

class TestStaticDriver:
    def test_returns_monthly_temperature(self):
        from instream.marine.domain import StaticDriver
        from instream.marine.config import MarineConfig, ZoneConfig, ZoneDriverData
        import datetime

        cfg = MarineConfig(
            zones=[ZoneConfig(name="Estuary", area_km2=50)],
            zone_connectivity=[],
            static_driver={
                "Estuary": ZoneDriverData(
                    temperature=[2,4,8,12,15,16,15,12,8,5,3,2],
                    salinity=[5]*12,
                    prey_index=[0.5]*12,
                    predation_risk=[0.1]*12,
                ),
            },
        )
        driver = StaticDriver(cfg)
        # January = index 0 = temperature 2
        conditions = driver.get_zone_conditions(datetime.date(2012, 1, 15))
        assert conditions["temperature"][0] == pytest.approx(2.0)
        # July = index 6 = temperature 15
        conditions = driver.get_zone_conditions(datetime.date(2012, 7, 15))
        assert conditions["temperature"][0] == pytest.approx(15.0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_marine.py::TestZoneState tests/test_marine.py::TestStaticDriver -v
```

- [ ] **Step 3: Implement ZoneState and StaticDriver**

Create `src/instream/marine/domain.py`:

```python
"""Marine domain — MarineDomain, ZoneState, StaticDriver, transitions."""
from dataclasses import dataclass
import numpy as np
from instream.state.life_stage import LifeStage


@dataclass
class ZoneState:
    """Environmental conditions per marine zone."""
    num_zones: int
    name: np.ndarray        # object array of strings
    temperature: np.ndarray  # float64 (num_zones,)
    salinity: np.ndarray
    prey_index: np.ndarray
    predation_risk: np.ndarray
    area_km2: np.ndarray

    @classmethod
    def zeros(cls, num_zones, names=None):
        if names is None:
            names = [f"Zone_{i}" for i in range(num_zones)]
        return cls(
            num_zones=num_zones,
            name=np.array(names, dtype=object),
            temperature=np.zeros(num_zones, dtype=np.float64),
            salinity=np.zeros(num_zones, dtype=np.float64),
            prey_index=np.zeros(num_zones, dtype=np.float64),
            predation_risk=np.zeros(num_zones, dtype=np.float64),
            area_km2=np.zeros(num_zones, dtype=np.float64),
        )


class StaticDriver:
    """Environmental driver using static monthly YAML tables."""

    def __init__(self, marine_config):
        self._config = marine_config
        self._zone_names = [z.name for z in marine_config.zones]

    def get_zone_conditions(self, date):
        """Return dict with arrays of conditions per zone for a given date."""
        month_idx = date.month - 1  # 0-based
        n = len(self._zone_names)
        temp = np.zeros(n, dtype=np.float64)
        sal = np.zeros(n, dtype=np.float64)
        prey = np.zeros(n, dtype=np.float64)
        pred = np.zeros(n, dtype=np.float64)
        for i, name in enumerate(self._zone_names):
            data = self._config.static_driver.get(name)
            if data:
                temp[i] = data.temperature[month_idx]
                sal[i] = data.salinity[month_idx]
                prey[i] = data.prey_index[month_idx]
                pred[i] = data.predation_risk[month_idx]
        return {"temperature": temp, "salinity": sal, "prey_index": prey, "predation_risk": pred}
```

- [ ] **Step 4: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_marine.py -v --tb=short
git add src/instream/marine/domain.py tests/test_marine.py
git commit -m "feat: add ZoneState dataclass and StaticDriver"
```

---

## Task 4: MarineDomain Class

**Files:**
- Modify: `src/instream/marine/domain.py`
- Test: `tests/test_marine.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_marine.py`:

```python
class TestMarineDomain:
    def test_daily_step_skips_freshwater_fish(self):
        from instream.marine.domain import MarineDomain, ZoneState
        from instream.state.trout_state import TroutState
        import datetime

        ts = TroutState.zeros(5)
        ts.alive[:3] = True
        ts.zone_idx[0] = 0  # marine
        ts.zone_idx[1] = -1  # freshwater
        ts.zone_idx[2] = 1  # marine
        ts.life_history[0] = int(LifeStage.SMOLT)
        ts.smolt_date[0] = datetime.date(2012, 5, 1).toordinal()
        ts.life_history[2] = int(LifeStage.OCEAN_JUVENILE)
        ts.smolt_date[2] = datetime.date(2011, 5, 1).toordinal()

        zs = ZoneState.zeros(3, names=["Estuary", "Coastal", "Baltic"])
        from instream.marine.config import MarineConfig, ZoneConfig
        cfg = MarineConfig(
            zones=[ZoneConfig(name="Estuary", area_km2=50),
                   ZoneConfig(name="Coastal", area_km2=500),
                   ZoneConfig(name="Baltic", area_km2=5000)],
            zone_connectivity=[[0,1],[1,2],[2,1]],
        )
        md = MarineDomain(ts, zs, cfg)
        # Should not crash — freshwater fish (idx 1) is skipped
        md.daily_step(datetime.date(2012, 6, 1))

    def test_sea_winters_increment_on_jan1(self):
        from instream.marine.domain import MarineDomain, ZoneState
        from instream.state.trout_state import TroutState
        import datetime

        ts = TroutState.zeros(2)
        ts.alive[0] = True
        ts.zone_idx[0] = 1
        ts.life_history[0] = int(LifeStage.OCEAN_JUVENILE)
        ts.sea_winters[0] = 0

        zs = ZoneState.zeros(3, names=["E", "C", "B"])
        from instream.marine.config import MarineConfig, ZoneConfig
        cfg = MarineConfig(
            zones=[ZoneConfig(name="E", area_km2=50),
                   ZoneConfig(name="C", area_km2=500),
                   ZoneConfig(name="B", area_km2=5000)],
            zone_connectivity=[[0,1],[1,2]],
        )
        md = MarineDomain(ts, zs, cfg)
        md.daily_step(datetime.date(2013, 1, 1))
        assert ts.sea_winters[0] == 1
```

- [ ] **Step 2: Implement MarineDomain**

Add to `src/instream/marine/domain.py`:

```python
class MarineDomain:
    """Marine domain — processes fish with zone_idx >= 0."""

    def __init__(self, trout_state, zone_state, marine_config):
        self.trout_state = trout_state
        self.zone_state = zone_state
        self.config = marine_config
        self.driver = StaticDriver(marine_config)
        # Build zone connectivity graph
        self._zone_graph = {}
        for edge in marine_config.zone_connectivity:
            src, dst = edge
            self._zone_graph.setdefault(src, []).append(dst)

    def update_environment(self, date):
        """Update zone conditions from driver."""
        conditions = self.driver.get_zone_conditions(date)
        self.zone_state.temperature[:] = conditions["temperature"]
        self.zone_state.salinity[:] = conditions["salinity"]
        self.zone_state.prey_index[:] = conditions["prey_index"]
        self.zone_state.predation_risk[:] = conditions["predation_risk"]

    def daily_step(self, current_date):
        """Process all marine fish for one day."""
        self.update_environment(current_date)
        ts = self.trout_state
        alive = ts.alive_indices()
        marine = alive[ts.zone_idx[alive] >= 0]

        if len(marine) == 0:
            return

        # Sea-winters increment on Jan 1
        if current_date.month == 1 and current_date.day == 1:
            ts.sea_winters[marine] += 1

        # Time-based zone migration
        for i in marine:
            days_at_sea = current_date.toordinal() - ts.smolt_date[i]
            zone = int(ts.zone_idx[i])
            lh = int(ts.life_history[i])

            # SMOLT in Estuary -> Coastal after 14 days
            if lh == LifeStage.SMOLT and zone == 0 and days_at_sea >= 14:
                next_zones = self._zone_graph.get(0, [])
                if next_zones:
                    ts.zone_idx[i] = next_zones[0]

            # SMOLT in Coastal -> Baltic after 30 days, become OCEAN_JUVENILE
            elif lh == LifeStage.SMOLT and zone >= 1 and days_at_sea >= 30:
                next_zones = self._zone_graph.get(int(ts.zone_idx[i]), [])
                if next_zones:
                    ts.zone_idx[i] = next_zones[0]
                ts.life_history[i] = int(LifeStage.OCEAN_JUVENILE)

            # OCEAN_JUVENILE -> OCEAN_ADULT after 1 sea-winter
            elif lh == LifeStage.OCEAN_JUVENILE and ts.sea_winters[i] >= 1:
                ts.life_history[i] = int(LifeStage.OCEAN_ADULT)

        # No growth, no survival — placeholder (100% survival)
```

- [ ] **Step 3: Update marine __init__.py exports**

```python
"""Marine domain for inSALMON anadromous lifecycle."""
from instream.marine.domain import MarineDomain, ZoneState, StaticDriver
from instream.marine.config import MarineConfig, ZoneConfig
```

- [ ] **Step 4: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_marine.py -v --tb=short
git add src/instream/marine/ tests/test_marine.py
git commit -m "feat: add MarineDomain with zone migration and sea-winters"
```

---

## Task 5: Freshwater Zone Guards

**Files:**
- Modify: `src/instream/model.py`
- Modify: `src/instream/model_environment.py`
- Modify: `src/instream/model_day_boundary.py`

This is the most invasive task. 10 locations need `zone_idx == -1` filtering.

- [ ] **Step 1: Add freshwater_alive computation in model.py step()**

In `model.py` step(), after `step_length = self.time_manager.advance()`, add:

```python
        # Compute freshwater-only alive mask for domain routing
        all_alive = self.trout_state.alive_indices()
        if hasattr(self, '_marine_domain') and self._marine_domain is not None:
            fw_mask = self.trout_state.zone_idx[all_alive] == -1
            freshwater_alive = all_alive[fw_mask]
        else:
            freshwater_alive = all_alive
```

- [ ] **Step 2: Guard habitat selection (model.py:60-73)**

Pass `freshwater_alive` to `select_habitat_and_activity` or guard the call. The simplest approach: temporarily set marine fish as non-alive during habitat selection, then restore. Better approach: add a `fish_mask` parameter. Read the function signature to decide.

For scaffolding, the simplest guard before the `select_habitat_and_activity` call:

```python
        # Temporarily mark marine fish as not-alive for freshwater processing
        marine_mask = self.trout_state.zone_idx >= 0
        was_alive = self.trout_state.alive.copy()
        self.trout_state.alive[marine_mask] = False

        select_habitat_and_activity(...)

        # Restore marine fish
        self.trout_state.alive[:] = was_alive
```

- [ ] **Step 3: Guard growth memory and fitness loops (model.py:76-101)**

Replace `alive = self.trout_state.alive_indices()` at line 76 with `freshwater_alive`:

```python
        for i in freshwater_alive:
            self.trout_state.growth_memory[i, substep] = ...
```

And the fitness EMA loop at line 88:

```python
        alive_after = self.trout_state.alive_indices()
        if hasattr(self, '_marine_domain') and self._marine_domain is not None:
            fw_after = alive_after[self.trout_state.zone_idx[alive_after] == -1]
        else:
            fw_after = alive_after
        for i in fw_after:
            ...
```

- [ ] **Step 4: Guard _do_survival (model_environment.py:150-240)**

In `_do_survival`, after computing `alive`:

```python
        # Exclude marine fish from freshwater survival
        if hasattr(self, '_marine_domain') and self._marine_domain is not None:
            fw_mask = self.trout_state.zone_idx[alive] == -1
            fw_alive = alive[fw_mask]
        else:
            fw_alive = alive
```

Use `fw_alive` instead of `alive` for all freshwater survival operations. Set `survival_probs[marine_alive] = 1.0` explicitly.

- [ ] **Step 5: Guard model_day_boundary.py loops**

In `_do_day_boundary`, add zone_idx guards to:
- Post-spawn mortality check (uses `alive_indices()`)
- `_do_spawning` (iterates alive fish, indexes reach_idx)
- `_apply_accumulated_growth` (already has cell_idx validity check — safe)
- `_do_migration` (already has life_history guard — safe)

For spawning, add at the start of `_do_spawning`:

```python
        alive = self.trout_state.alive_indices()
        # Exclude marine fish from freshwater spawning
        alive = alive[self.trout_state.zone_idx[alive] == -1]
```

- [ ] **Step 6: Run full test suite**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

Expected: 729+ passed (all existing tests unaffected — no marine fish present in existing configs).

- [ ] **Step 7: Commit**

```bash
git add src/instream/model.py src/instream/model_environment.py src/instream/model_day_boundary.py
git commit -m "feat: add zone_idx freshwater guards to 10 alive-fish loops

Marine fish (zone_idx >= 0) are excluded from freshwater habitat selection,
growth memory, fitness EMA, survival, and spawning. Prevents silent
corruption from reach_idx=-1 wrap-around."
```

---

## Task 6: Smolt Exit at River Mouth

**Files:**
- Modify: `src/instream/modules/migration.py`
- Test: `tests/test_marine.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_marine.py`:

```python
class TestSmoltTransition:
    def test_parr_at_river_mouth_becomes_smolt(self):
        from instream.state.trout_state import TroutState
        from instream.modules.migration import migrate_fish_downstream
        import datetime

        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.life_history[0] = int(LifeStage.PARR)
        ts.reach_idx[0] = 0
        ts.length[0] = 15.0
        ts.smolt_readiness[0] = 0.9  # above threshold

        reach_graph = {0: []}  # no downstream — river mouth
        marine_config_present = True
        smolt_threshold = 0.8
        smolt_min_length = 12.0
        current_date = datetime.date(2012, 5, 15)

        outmigrants = migrate_fish_downstream(
            ts, 0, reach_graph,
            marine_config=marine_config_present,
            smolt_readiness_threshold=smolt_threshold,
            smolt_min_length=smolt_min_length,
            current_date=current_date,
        )

        assert ts.alive[0] == True  # NOT killed
        assert ts.life_history[0] == int(LifeStage.SMOLT)
        assert ts.zone_idx[0] == 0  # estuary
        assert ts.natal_reach_idx[0] == 0
        assert ts.smolt_date[0] == current_date.toordinal()
        assert ts.cell_idx[0] == -1
        assert ts.reach_idx[0] == -1
        assert len(outmigrants) == 1  # still recorded as outmigrant

    def test_parr_below_min_length_killed_not_smolt(self):
        from instream.state.trout_state import TroutState
        from instream.modules.migration import migrate_fish_downstream
        import datetime

        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.life_history[0] = int(LifeStage.PARR)
        ts.reach_idx[0] = 0
        ts.length[0] = 8.0  # below min
        ts.smolt_readiness[0] = 0.9

        reach_graph = {0: []}
        outmigrants = migrate_fish_downstream(
            ts, 0, reach_graph,
            marine_config=True, smolt_readiness_threshold=0.8,
            smolt_min_length=12.0, current_date=datetime.date(2012, 5, 15),
        )
        assert ts.alive[0] == False  # killed, not smolt
        assert ts.zone_idx[0] == -1  # stayed freshwater

    def test_no_marine_config_kills_as_before(self):
        from instream.state.trout_state import TroutState
        from instream.modules.migration import migrate_fish_downstream

        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.life_history[0] = int(LifeStage.PARR)
        ts.reach_idx[0] = 0

        reach_graph = {0: []}
        outmigrants = migrate_fish_downstream(ts, 0, reach_graph)
        assert ts.alive[0] == False  # original behavior
```

- [ ] **Step 2: Modify migrate_fish_downstream**

Update signature to accept optional marine parameters:

```python
def migrate_fish_downstream(trout_state, fish_idx, reach_graph,
                             marine_config=None, smolt_readiness_threshold=0.8,
                             smolt_min_length=12.0, current_date=None):
    """Move a fish downstream, or transition to smolt/outmigrant."""
    outmigrants = []
    current_reach = int(trout_state.reach_idx[fish_idx])
    downstream = reach_graph.get(current_reach, [])
    if len(downstream) > 0:
        trout_state.reach_idx[fish_idx] = downstream[0]
    else:
        # No downstream reach — river mouth
        outmigrants.append({
            "species_idx": int(trout_state.species_idx[fish_idx]),
            "length": float(trout_state.length[fish_idx]),
            "reach_idx": current_reach,
        })

        # Check for smolt transition
        if (marine_config is not None
            and trout_state.life_history[fish_idx] == LifeStage.PARR
            and trout_state.smolt_readiness[fish_idx] >= smolt_readiness_threshold
            and trout_state.length[fish_idx] >= smolt_min_length
            and current_date is not None):
            # Transition to marine domain
            trout_state.life_history[fish_idx] = int(LifeStage.SMOLT)
            trout_state.zone_idx[fish_idx] = 0  # estuary
            trout_state.natal_reach_idx[fish_idx] = current_reach
            trout_state.smolt_date[fish_idx] = current_date.toordinal()
            trout_state.cell_idx[fish_idx] = -1
            trout_state.reach_idx[fish_idx] = -1
        else:
            trout_state.alive[fish_idx] = False
    return outmigrants
```

- [ ] **Step 3: Update _do_migration caller in model_day_boundary.py**

Find the `migrate_fish_downstream` call and pass marine config params:

```python
outmigrants = migrate_fish_downstream(
    self.trout_state, i, self._reach_graph,
    marine_config=getattr(self.config, 'marine', None),
    smolt_readiness_threshold=getattr(self.config.marine, 'smolt_readiness_threshold', 0.8) if self.config.marine else 0.8,
    smolt_min_length=getattr(self.config.marine, 'smolt_min_length', 12.0) if self.config.marine else 12.0,
    current_date=self.time_manager.current_date,
)
```

- [ ] **Step 4: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_marine.py::TestSmoltTransition tests/test_migration.py -v --tb=short
git add src/instream/modules/migration.py src/instream/model_day_boundary.py tests/test_marine.py
git commit -m "feat: smolt transition at river mouth instead of kill when marine config present"
```

---

## Task 7: Smolt Readiness Accumulation

**Files:**
- Modify: `src/instream/model.py`
- Modify: `src/instream/model_environment.py`
- Test: `tests/test_marine.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_marine.py`:

```python
class TestSmoltReadiness:
    def test_readiness_accumulates_in_spring(self):
        from instream.marine.domain import accumulate_smolt_readiness
        import numpy as np
        readiness = np.array([0.0, 0.5])
        lengths = np.array([15.0, 8.0])
        life_history = np.array([int(LifeStage.PARR), int(LifeStage.FRY)])
        day_length = 14.0  # spring
        max_day_length = 18.0
        temperature = 10.0
        optimal_temp = 10.0
        photo_weight = 0.6
        temp_weight = 0.4
        doy = 120  # May — inside window

        accumulate_smolt_readiness(
            readiness, life_history, lengths,
            day_length, max_day_length, temperature, optimal_temp,
            photo_weight, temp_weight, doy,
            window_start=90, window_end=180, min_length=12.0,
        )
        assert readiness[0] > 0.0  # PARR above min_length accumulated
        assert readiness[1] == 0.0  # FRY not checked

    def test_readiness_zero_outside_window(self):
        from instream.marine.domain import accumulate_smolt_readiness
        import numpy as np
        readiness = np.array([0.0])
        accumulate_smolt_readiness(
            readiness,
            life_history=np.array([int(LifeStage.PARR)]),
            lengths=np.array([15.0]),
            day_length=10.0, max_day_length=18.0,
            temperature=10.0, optimal_temp=10.0,
            photo_weight=0.6, temp_weight=0.4,
            doy=300,  # October — outside window
            window_start=90, window_end=180, min_length=12.0,
        )
        assert readiness[0] == 0.0  # no accumulation outside window
```

- [ ] **Step 2: Implement accumulate_smolt_readiness**

Add to `src/instream/marine/domain.py`:

```python
def accumulate_smolt_readiness(readiness, life_history, lengths,
                                day_length, max_day_length,
                                temperature, optimal_temp,
                                photo_weight, temp_weight,
                                doy, window_start=90, window_end=180,
                                min_length=12.0):
    """Accumulate smolt readiness for PARR fish during spring window."""
    if doy < window_start or doy > window_end:
        return  # outside smolt window

    photo_signal = day_length / max(max_day_length, 1.0)
    temp_signal = max(0.0, 1.0 - abs(temperature - optimal_temp) / max(optimal_temp, 1.0))
    increment = photo_weight * photo_signal + temp_weight * temp_signal

    for idx in range(len(readiness)):
        if (life_history[idx] == LifeStage.PARR
                and lengths[idx] >= min_length):
            readiness[idx] += increment
```

- [ ] **Step 3: Cache day_length in model_environment.py**

In `_update_environment`, after the `compute_light` call, store:

```python
self._day_length = dl  # cache for smolt readiness
```

- [ ] **Step 4: Wire into model.py step() — call after day boundary**

In `model.py` step(), after `_do_day_boundary`, add smolt readiness:

```python
        if is_boundary and hasattr(self, '_marine_domain') and self._marine_domain is not None:
            from instream.marine.domain import accumulate_smolt_readiness
            mc = self.config.marine
            accumulate_smolt_readiness(
                self.trout_state.smolt_readiness,
                self.trout_state.life_history,
                self.trout_state.length,
                day_length=getattr(self, '_day_length', 12.0),
                max_day_length=18.0,
                temperature=float(self.reach_state.temperature[0]),
                optimal_temp=mc.smolt_temperature_optimal,
                photo_weight=mc.smolt_photoperiod_weight,
                temp_weight=mc.smolt_temperature_weight,
                doy=self.time_manager.julian_date,
                window_start=mc.smolt_window_start_doy,
                window_end=mc.smolt_window_end_doy,
                min_length=mc.smolt_min_length,
            )
            # Reset readiness on Jan 1
            if self.time_manager.julian_date == 1:
                self.trout_state.smolt_readiness[:] = 0.0
```

- [ ] **Step 5: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_marine.py tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
git add src/instream/marine/domain.py src/instream/model.py src/instream/model_environment.py tests/test_marine.py
git commit -m "feat: add smolt readiness accumulation with spring window and day_length caching"
```

---

## Task 8: Adult Return

**Files:**
- Modify: `src/instream/marine/domain.py`
- Modify: `src/instream/model.py`
- Test: `tests/test_marine.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_marine.py`:

```python
class TestAdultReturn:
    def test_ocean_adult_returns_in_spring(self):
        from instream.marine.domain import check_adult_return
        from instream.state.trout_state import TroutState
        import datetime

        ts = TroutState.zeros(3)
        ts.alive[0] = True
        ts.zone_idx[0] = 2
        ts.life_history[0] = int(LifeStage.OCEAN_ADULT)
        ts.sea_winters[0] = 2
        ts.condition[0] = 0.8
        ts.natal_reach_idx[0] = 0

        # Need a cell lookup for natal reach
        reach_cells = {0: [5, 10, 15]}  # cells in reach 0

        check_adult_return(
            ts, reach_cells,
            return_sea_winters=2, return_condition_min=0.0,
            current_date=datetime.date(2013, 5, 1),  # spring
            rng=np.random.default_rng(42),
        )

        assert ts.life_history[0] == int(LifeStage.RETURNING_ADULT)
        assert ts.zone_idx[0] == -1
        assert ts.reach_idx[0] == 0
        assert ts.cell_idx[0] in [5, 10, 15]  # valid cell in natal reach

    def test_no_return_outside_spring(self):
        from instream.marine.domain import check_adult_return
        from instream.state.trout_state import TroutState
        import datetime

        ts = TroutState.zeros(2)
        ts.alive[0] = True
        ts.zone_idx[0] = 2
        ts.life_history[0] = int(LifeStage.OCEAN_ADULT)
        ts.sea_winters[0] = 2
        ts.condition[0] = 0.8
        ts.natal_reach_idx[0] = 0

        check_adult_return(
            ts, {0: [5]},
            return_sea_winters=2, return_condition_min=0.0,
            current_date=datetime.date(2013, 11, 1),  # autumn
            rng=np.random.default_rng(42),
        )

        assert ts.life_history[0] == int(LifeStage.OCEAN_ADULT)  # no change
        assert ts.zone_idx[0] == 2  # still marine
```

- [ ] **Step 2: Implement check_adult_return**

Add to `src/instream/marine/domain.py`:

```python
def check_adult_return(trout_state, reach_cells, return_sea_winters,
                        return_condition_min, current_date, rng):
    """Check OCEAN_ADULT fish for return to freshwater."""
    doy = current_date.timetuple().tm_yday
    is_spring = 90 <= doy <= 180

    if not is_spring:
        return

    alive = trout_state.alive_indices()
    for i in alive:
        if (trout_state.zone_idx[i] >= 0
            and trout_state.life_history[i] == LifeStage.OCEAN_ADULT
            and trout_state.sea_winters[i] >= return_sea_winters
            and trout_state.condition[i] >= return_condition_min):

            natal = int(trout_state.natal_reach_idx[i])
            cells = reach_cells.get(natal, [])
            if not cells:
                continue  # no valid cells in natal reach

            trout_state.life_history[i] = int(LifeStage.RETURNING_ADULT)
            trout_state.zone_idx[i] = -1
            trout_state.reach_idx[i] = natal
            trout_state.cell_idx[i] = int(rng.choice(cells))
```

- [ ] **Step 3: Wire into model.py step() after smolt readiness**

```python
            # Adult return check
            from instream.marine.domain import check_adult_return
            # Build reach->cells mapping
            cs = self.fem_space.cell_state
            reach_cells = {}
            for r_idx in range(len(self.reach_order)):
                wet = np.where((cs.reach_idx == r_idx) & (cs.depth > 0))[0]
                if len(wet) > 0:
                    reach_cells[r_idx] = wet.tolist()
            check_adult_return(
                self.trout_state, reach_cells,
                return_sea_winters=mc.return_sea_winters,
                return_condition_min=mc.return_condition_min,
                current_date=self.time_manager.current_date,
                rng=self.rng,
            )
```

- [ ] **Step 4: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_marine.py tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
git add src/instream/marine/domain.py src/instream/model.py tests/test_marine.py
git commit -m "feat: add adult return from marine to freshwater with valid cell_idx"
```

---

## Task 9: Model Integration — MarineDomain in step()

**Files:**
- Modify: `src/instream/model_init.py`
- Modify: `src/instream/model.py`
- Modify: `src/instream/modules/spawning.py` (natal_reach_idx)

- [ ] **Step 1: Initialize MarineDomain in _build_model**

In `src/instream/model_init.py`, at the end of `_build_model`:

```python
        # Marine domain (optional)
        self._marine_domain = None
        if self.config.marine is not None:
            from instream.marine.domain import MarineDomain, ZoneState
            mc = self.config.marine
            zone_names = [z.name for z in mc.zones]
            zone_areas = np.array([z.area_km2 for z in mc.zones])
            zs = ZoneState.zeros(len(mc.zones), names=zone_names)
            zs.area_km2[:] = zone_areas
            self._marine_domain = MarineDomain(self.trout_state, zs, mc)
```

- [ ] **Step 2: Add marine daily_step call in model.py step()**

After the freshwater survival block, before `if is_boundary`:

```python
        # Marine domain daily step (if configured)
        if self._marine_domain is not None:
            self._marine_domain.daily_step(self.time_manager.current_date)
```

- [ ] **Step 3: Set natal_reach_idx on emergence**

In `src/instream/modules/spawning.py`, in `redd_emergence`, after setting `trout_state.reach_idx[slots]`:

```python
        if hasattr(trout_state, 'natal_reach_idx'):
            trout_state.natal_reach_idx[slots] = redd_reach_idx
```

- [ ] **Step 4: Run full suite**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

Expected: 729+ passed (no marine config in existing tests = no marine code activated).

- [ ] **Step 5: Commit**

```bash
git add src/instream/model_init.py src/instream/model.py src/instream/modules/spawning.py
git commit -m "feat: integrate MarineDomain into model step() and set natal_reach_idx on emergence"
```

---

## Task 10: Example Marine Config and End-to-End Test

**Files:**
- Create: `configs/example_marine.yaml`
- Create: `tests/test_marine_e2e.py`

- [ ] **Step 1: Create example_marine.yaml**

Copy `configs/example_a.yaml` and add the marine section from the spec.

- [ ] **Step 2: Write end-to-end test**

Create `tests/test_marine_e2e.py`:

```python
"""End-to-end test: full lifecycle freshwater → marine → return."""
import pytest
import numpy as np
from pathlib import Path
from instream.state.life_stage import LifeStage

CONFIGS = Path(__file__).parent.parent / "configs"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.slow
class TestMarineLifecycleE2E:
    @pytest.fixture(scope="class")
    def model(self):
        from instream.model import InSTREAMModel
        import datetime
        start = datetime.date(2011, 4, 1)
        end_date = (start + datetime.timedelta(days=730)).isoformat()
        m = InSTREAMModel(
            CONFIGS / "example_marine.yaml",
            data_dir=FIXTURES / "example_a",
            end_date_override=end_date,
        )
        m.run()
        return m

    def test_some_fish_smoltified(self, model):
        ts = model.trout_state
        smolted = np.any(ts.smolt_date >= 0)
        assert smolted, "No fish ever smoltified"

    def test_some_fish_returned(self, model):
        ts = model.trout_state
        alive = ts.alive_indices()
        returning = np.sum(ts.life_history[alive] == int(LifeStage.RETURNING_ADULT))
        spawners = np.sum(ts.life_history[alive] == int(LifeStage.SPAWNER))
        assert returning + spawners > 0, "No fish returned from marine domain"

    def test_returned_fish_have_valid_cell(self, model):
        ts = model.trout_state
        alive = ts.alive_indices()
        returned = alive[ts.natal_reach_idx[alive] >= 0]
        fw = returned[ts.zone_idx[returned] == -1]
        if len(fw) > 0:
            assert np.all(ts.cell_idx[fw] >= 0), "Returned fish have invalid cell_idx"

    def test_freshwater_still_works(self, model):
        ts = model.trout_state
        alive = ts.alive.sum()
        assert alive > 0, "Population went extinct"


@pytest.mark.slow
class TestBackwardCompatibility:
    def test_no_marine_config_unchanged(self):
        from instream.model import InSTREAMModel
        import datetime
        start = datetime.date(2011, 4, 1)
        end_date = (start + datetime.timedelta(days=30)).isoformat()
        m = InSTREAMModel(
            CONFIGS / "example_a.yaml",
            data_dir=FIXTURES / "example_a",
            end_date_override=end_date,
        )
        m.run()
        ts = m.trout_state
        alive = ts.alive_indices()
        assert np.all(ts.zone_idx[alive] == -1), "Fish entered marine domain without config"
```

- [ ] **Step 3: Run end-to-end test**

```bash
micromamba run -n shiny python -m pytest tests/test_marine_e2e.py -v --tb=long -m slow
```

- [ ] **Step 4: Run full suite**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 5: Commit**

```bash
git add configs/example_marine.yaml tests/test_marine_e2e.py
git commit -m "feat: add example marine config and end-to-end lifecycle test"
```

---

## Task 11: Documentation and Release v0.14.0

**Files:**
- Modify: `CHANGELOG.md`, `README.md`, `pyproject.toml`, `src/instream/__init__.py`

- [ ] **Step 1: Run full test suite**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 2: Run frontend smoke test**

```bash
micromamba run -n shiny python -m pytest tests/test_app_smoke.py tests/test_simulation_wrapper.py -v --tb=short
```

- [ ] **Step 3: Update CHANGELOG.md**

Add v0.14.0 section with: MarineDomain, ZoneState, StaticDriver, lifecycle transitions, zone_idx guards, example_marine.yaml.

- [ ] **Step 4: Bump version to 0.14.0**

In `pyproject.toml` and `src/instream/__init__.py`.

- [ ] **Step 5: Commit, tag, push**

```bash
git add CHANGELOG.md README.md pyproject.toml src/instream/__init__.py
git commit -m "release: v0.14.0 — marine domain scaffolding, lifecycle transitions"
git tag v0.14.0
git push origin master --tags
```

---

## Summary

| Task | Description | Est. Time |
|------|-------------|-----------|
| 1 | TroutState 5 marine fields + zeros() | 0.5 days |
| 2 | MarineConfig Pydantic models | 0.5 days |
| 3 | ZoneState + StaticDriver | 1 day |
| 4 | MarineDomain class (zone migration, sea-winters) | 1.5 days |
| 5 | Freshwater zone_idx guards (10 locations) | 2 days |
| 6 | Smolt exit at river mouth (migration.py) | 1 day |
| 7 | Smolt readiness accumulation + day_length caching | 1.5 days |
| 8 | Adult return with valid cell_idx | 1 day |
| 9 | Model integration (init, step, natal_reach_idx) | 1 day |
| 10 | Example marine config + E2E test + backward compat | 1.5 days |
| 11 | Documentation and release | 1 day |

**Task estimates sum to 12.5 days. With buffer: 14 working days.** Best case 11, worst case 18.

---

## Out of Scope (v0.15.0+)

- Marine growth bioenergetics (Sub-project B)
- 7 marine survival sources (Sub-project B)
- Fishing module with gear selectivity (Sub-project B)
- NetCDF environmental driver (Sub-project C)
- WMS environmental driver (Sub-project C)
- FreshwaterDomain class extraction from mixins
- Multi-generation simulation
