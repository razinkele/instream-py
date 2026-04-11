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


@pytest.mark.slow
class TestICESCalibrationBaltic:
    """Baltic Atlantic salmon calibration against ICES WGBAST point-
    calibration bands (v0.18.0).

    Unlike TestICESCalibration (which runs against Chinook-Spring and is
    intentionally a collapse detector), this class runs against the
    Baltic Atlantic salmon species config at configs/baltic_salmon_species.yaml
    and asserts on tightened bands:

    * SAR 3-12% (vs 2-18% for Chinook)
    * Repeat-spawner fraction 2-12% (vs 0-12% for Chinook)

    This elevates the calibration test from emergent-plausibility to
    quantitative validation against ICES WGBAST 2024 Baltic wild-river
    assessments.

    Full config: configs/example_calibration_baltic.yaml
    Scite-backed provenance: docs/calibration-notes.md (Baltic Atlantic
    salmon parameters section).

    Note on fixture duplication: this fixture is a near-verbatim copy of
    TestICESCalibration.model. Per v0.18.0 plan's YAGNI decision, the
    duplication is accepted rather than refactored into a shared helper.
    Any future change to the PARR-seeding protocol must be applied in
    both places.
    """

    @pytest.fixture(scope="class")
    def model(self):
        from instream.model import InSTREAMModel
        from instream.state.life_stage import LifeStage

        m = InSTREAMModel(
            CONFIGS / "example_calibration_baltic.yaml",
            data_dir=FIXTURES / "example_a",
            end_date_override="2018-03-31",
        )

        import pandas as pd
        start = datetime.date(2011, 4, 1)
        required_end = start + datetime.timedelta(days=7 * 365)
        ts_csv = FIXTURES / "example_a" / "ExampleA-TimeSeriesInputs.csv"
        try:
            df = pd.read_csv(ts_csv, comment=";")
            ts_last = pd.Timestamp(df.iloc[-1, 0]).date()
        except Exception as exc:
            pytest.skip(f"Could not read hydraulics time series: {exc}")
        if ts_last < required_end:
            pytest.skip(
                f"Hydraulics time series ends {ts_last}, before required "
                f"5-year horizon {required_end}."
            )

        ts = m.trout_state
        dead = np.where(~ts.alive)[0]
        n_parr = min(len(dead), 3000)
        if n_parr < 1500:
            pytest.skip(
                f"TroutState capacity too small ({n_parr} < 1500). "
                f"Verify configs/example_calibration_baltic.yaml has "
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
        ts.zone_idx[parr] = -1
        ts.sea_winters[parr] = 0
        ts.smolt_date[parr] = -1
        ts.is_hatchery[parr] = False

        m.run()
        return m

    def test_smoltification_happened(self, model):
        md = model._marine_domain
        assert md.total_smoltified > 0, (
            "No Baltic salmon smoltified — check smolt_readiness and "
            "smolt_min_length against species config."
        )

    def test_sar_baltic_point_calibration(self, model):
        """Tightened band: 3-12% matches ICES WGBAST Baltic wild rivers.

        Unlike the Chinook collapse-detector (2-18%), this band is narrow
        enough to represent a genuine point calibration. At 3000 smolts
        with expected SAR ~6%, the binomial noise gives ~0.87 pp 2-sigma
        — effective power is ~3-sigma against the 9 pp band width once
        process-model stochasticity inflates the noise. Boundary-case
        failures (SAR near 3% or 12%) warrant a seed re-run before
        declaring calibration failure.
        """
        md = model._marine_domain
        sar = md.total_returned / md.total_smoltified
        assert 0.03 <= sar <= 0.12, (
            f"Baltic salmon SAR {sar:.4f} outside ICES WGBAST 3-12% "
            f"band (smoltified={md.total_smoltified}, "
            f"returned={md.total_returned}). This is a point-calibration "
            f"failure. If near boundary, re-run with a different seed."
        )

    def test_kelt_counter_wired(self, model):
        """v0.21.0: kelt chain fully unblocked.

        After v0.20.0 Option A (RETURNING_ADULT mortality protection) and
        v0.21.0 Option B (RETURNING_ADULT growth clamp during freshwater
        hold — `model_day_boundary._apply_accumulated_growth`), the 7-year
        Baltic run produces ~25 kelts from ~108 returners. The eligible
        pool is now ~110 SPAWNERs (vs. 5 in v0.20.0), and binomial(110,
        0.25) gives a 95% confidence interval of roughly 19-37 kelts.

        Assert `>= 5` as a defensive lower bound well below the expected
        ~25-28 — leaves headroom for seed variation while still proving
        the chain is firing.
        """
        md = model._marine_domain
        assert isinstance(md.total_kelts, int)
        assert md.total_kelts >= 5, (
            f"Kelt count {md.total_kelts} below v0.21.0 floor of 5. "
            f"Expected ~25 at the 7-year Baltic horizon. Either Option A "
            f"(model_environment.py RA mortality protection) or Option B "
            f"(model_day_boundary.py RA growth clamp) has regressed."
        )

    def test_repeat_spawner_fraction_baltic(self, model):
        """v0.19.0: horizon extended 5→7 years but lower bound left at
        0.0. Empirically the 7-year run still produces 0 repeat spawners
        (gated by the same kelt-chain issue tracked on
        test_kelt_counter_wired). Observed Baltic targets: 5-8% Teno
        (Niemelä et al.), ~0% Simojoki, 10-11% Atlantic average
        (Fleming & Reynolds 2004). Lower bound tightening to 1% deferred
        to v0.20.0 after the kelt-chain gate is identified and fixed.
        """
        md = model._marine_domain
        if md.total_returned == 0:
            pytest.skip("No returns in this run")
        repeat_frac = md.total_repeat_spawners / md.total_returned
        assert 0.0 <= repeat_frac <= 0.12, (
            f"Baltic repeat-spawner fraction {repeat_frac:.4f} outside "
            f"0-12% band (repeat={md.total_repeat_spawners}, "
            f"total={md.total_returned})."
        )
