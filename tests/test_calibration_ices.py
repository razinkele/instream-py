"""ICES WGBAST end-to-end calibration test (v0.17.0 Phase 4).

Asserts that the full marine-enabled inSALMON pipeline produces emergent
cohort behaviour inside Atlantic-salmon plausibility bands over a 5-year
run with a 3000-PARR pre-seeded cohort.

Reference: ICES WGBAST 2024 Baltic Salmon and Sea Trout Assessment Working
Group reports 2-15% smolt-to-adult return for Baltic wild rivers. The
upper band here is stretched to 18% to absorb iteroparous-return inflation
(~1.11x at 10% realized repeat rate) and stochastic tail variance.

SPECIES MISMATCH DISCLAIMER: This test runs against a Chinook-Spring
config because that is the only anadromous species currently in the
example configs. The bioenergetics parameters are nominally Pacific
Chinook, not Baltic Atlantic salmon. The test therefore validates
*emergent cohort plausibility* under the v0.17.0 marine ecology pipeline
— not species-specific NetLogo parity. Full species-specific calibration
is out-of-scope for v0.17.0 and blocked on a dedicated Baltic salmon
config (v0.18.0 candidate).

See docs/calibration-notes.md (written in Task 4.6) for scite-backed
provenance of every tuned parameter.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import numpy as np
import pytest

CONFIGS = Path(__file__).parent.parent / "configs"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.slow
class TestICESCalibration:
    """5-year Baltic salmon cohort calibration against ICES WGBAST bands."""

    @pytest.fixture(scope="class")
    def model(self):
        from instream.model import InSTREAMModel
        from instream.state.life_stage import LifeStage

        # end_date_override is defense-in-depth against a missing or
        # mis-edited example_calibration.yaml. If the YAML's end_date
        # is already 2016-03-31 this override is a no-op.
        m = InSTREAMModel(
            CONFIGS / "example_calibration.yaml",
            data_dir=FIXTURES / "example_a",
            end_date_override="2016-03-31",
        )

        # Hard skip if the hydraulics time series cannot support a
        # 5-year run. We check the actual CSV last row, NOT
        # m.time_manager._end_date — the latter always reflects
        # end_date_override and so never surfaces CSV-coverage issues.
        import pandas as pd
        start = datetime.date(2011, 4, 1)
        required_end = start + datetime.timedelta(days=5 * 365)
        ts_csv = FIXTURES / "example_a" / "ExampleA-TimeSeriesInputs.csv"
        try:
            df = pd.read_csv(ts_csv, comment=";")
            ts_last_raw = df.iloc[-1, 0]
            ts_last = pd.Timestamp(ts_last_raw).date()
        except Exception as exc:
            pytest.skip(
                f"Could not read hydraulics time series last row "
                f"from {ts_csv}: {exc}"
            )
        if ts_last < required_end:
            pytest.skip(
                f"Hydraulics time series ends {ts_last}, before "
                f"required 5-year horizon {required_end}. Either "
                f"extend the time series or shorten the calibration "
                f"horizon — the SAR test cannot run meaningfully "
                f"against a truncated ocean window."
            )

        # Allocate 3000 PARR into dead TroutState capacity. Relabelling
        # pre-alive fish (as the earlier E2E fixture did) yields only
        # 50-200 fish and makes the SAR assertion stochastically fragile.
        ts = m.trout_state
        dead = np.where(~ts.alive)[0]
        n_parr = min(len(dead), 3000)
        if n_parr < 1500:
            pytest.skip(
                f"TroutState capacity too small for calibration test "
                f"(only {n_parr} dead slots available, need >=1500). "
                f"Verify configs/example_calibration.yaml has "
                f"trout_capacity >= 6000."
            )
        parr = dead[:n_parr]
        sp_cfg = m.config.species[m.species_order[0]]

        ts.alive[parr] = True
        ts.species_idx[parr] = 0
        ts.life_history[parr] = int(LifeStage.PARR)
        ts.age[parr] = 1
        ts.length[parr] = 15.0
        ts.weight[parr] = sp_cfg.weight_A * 15.0 ** sp_cfg.weight_B
        ts.condition[parr] = 1.0
        ts.smolt_readiness[parr] = 0.9
        ts.fitness_memory[parr] = 0.5
        ts.reach_idx[parr] = 0
        ts.natal_reach_idx[parr] = 0
        # Fresh marine state.
        ts.zone_idx[parr] = -1
        ts.sea_winters[parr] = 0
        ts.smolt_date[parr] = -1
        ts.is_hatchery[parr] = False

        m.run()
        return m

    def test_smoltification_happened(self, model):
        """Gate: if no fish smoltified, the pipeline is broken and every
        downstream assertion is moot. Fail fast with a clear message."""
        md = model._marine_domain
        assert md.total_smoltified > 0, (
            "No fish smoltified during the 5-year run. Either the "
            "pre-seeded PARR cohort never reached the river mouth, or "
            "the smolt-readiness / smolt-min-length thresholds blocked "
            "them all. Inspect model._do_migration wiring."
        )

    def test_smolt_to_adult_survival_plausible(self, model):
        """SAR should land in a broad plausibility band. This is a
        **collapse detector**, not a quantitative 5% vs 10% discriminator
        — at a 3000-smolt cohort the 2-sigma noise on SAR is ~0.8 pp,
        so the 2-18% band (16 pp) is 20x the noise.

        Species mismatch: the test runs against a Chinook-Spring config
        (Pacific semelparous) with Atlantic-salmon hazard parameters.
        Chinook CMax peaks above Baltic thermal optima (Handeland et al.
        2008), so SAR will run systematically lower than an Atlantic
        cohort under the same hazards. The 2% lower bound is therefore
        the fragile edge for THIS species, not 18%.

        v0.18.0 candidate: dedicated Baltic Atlantic salmon config + 3-12%
        band for genuine point calibration.
        """
        md = model._marine_domain
        sar = md.total_returned / md.total_smoltified
        assert 0.02 <= sar <= 0.18, (
            f"Smolt-to-adult return {sar:.4f} outside 2-18% collapse "
            f"band (smoltified={md.total_smoltified}, "
            f"returned={md.total_returned}). "
            f"If SAR < 2%, cohort has collapsed — loosen hazards. "
            f"If SAR > 18%, hazards are absent — check that "
            f"apply_marine_survival runs in MarineDomain.daily_step."
        )

    def test_some_fish_became_kelts(self, model):
        """With a 3000-smolt cohort and 0.25 river-exit kelt probability,
        expect ~25-125 kelts over the 5-year horizon. > 0 is 5-sigma safe."""
        md = model._marine_domain
        assert md.total_kelts > 0, (
            f"No kelts produced (returned={md.total_returned}, "
            f"smoltified={md.total_smoltified}). "
            f"Check apply_post_spawn_kelt_survival wiring in "
            f"_do_day_boundary and verify species.kelt_survival_prob > 0."
        )

    def test_repeat_spawner_fraction_baltic_range(self, model):
        """Baltic repeat-spawner rates: Niemelä et al. 2006 on Teno
        ~5-8%, Simojoki near nil, Atlantic-average ~10-11% (Fleming &
        Reynolds 2004). Band 0-12% covers the full range of Baltic rivers
        plus a small rng tail."""
        md = model._marine_domain
        if md.total_returned == 0:
            pytest.skip("No returns in this run — cannot compute repeat fraction")
        repeat_frac = md.total_repeat_spawners / md.total_returned
        assert 0.0 <= repeat_frac <= 0.12, (
            f"Repeat-spawner fraction {repeat_frac:.4f} outside plausible "
            f"Baltic 0-12% range (repeat={md.total_repeat_spawners}, "
            f"total={md.total_returned})."
        )

    def test_counters_are_plain_ints(self, model):
        """v0.17.0 counter type contract regression guard."""
        md = model._marine_domain
        for name in ("total_smoltified", "total_returned",
                     "total_kelts", "total_repeat_spawners"):
            val = getattr(md, name)
            assert type(val) is int, (
                f"MarineDomain.{name} should be a plain int, got "
                f"{type(val).__name__}"
            )
